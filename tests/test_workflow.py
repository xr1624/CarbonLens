from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import pytest
from src.access import authenticate
from src.agent import run_agent, review_case
from src.cases import Case, now, snapshot_tables, encode_case, decode_case
from src.settings import Settings
from src.storage import Store, QuotaError, ConflictError
from src.validation import load_csv

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def case():
    tables = {kind: load_csv(ROOT / 'data' / f'{kind}.csv', kind) for kind in ('funds', 'holdings', 'benchmarks')}
    fund = tables['funds'].iloc[0]
    return Case('test-case', fund.fund_id, fund.fund_name, 'Synthetic Data', fund.esg_claim, now(), None,
                snapshot=snapshot_tables(tables), mode='Mock Mode')

@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{(tmp_path / 'cases.sqlite3').as_posix()}")

def test_mock_and_roundtrip(case):
    result = run_agent(case, Settings())
    assert result.result.fund_waci == Decimal('50')
    assert result.extraction.model == 'Mock Mode'
    assert decode_case(encode_case(result)) == result
    assert 'calculate_waci' in [e.tool for e in result.events]

def test_owner_isolation_and_versions(case, store):
    saved = store.save('alice', case)
    assert store.list_cases('bob') == []
    assert store.history('bob', case.case_id) == []
    with pytest.raises(ConflictError):
        store.save('bob', saved)
    changed = store.save('alice', replace(saved, review_status='已退回'))
    assert changed.revision == 2
    assert len(store.history('alice', case.case_id)) == 2
    with pytest.raises(ConflictError):
        store.save('alice', saved)

def test_quota_is_atomic_and_duplicate_is_blocked(store):
    store.reserve_call('alice', 'run1', 1, 2)
    with pytest.raises(QuotaError):
        store.reserve_call('alice', 'run2', 1, 2)
    store.reserve_call('bob', 'run3', 1, 2)
    with pytest.raises(QuotaError):
        store.reserve_call('carol', 'run4', 1, 2)
    with pytest.raises(QuotaError):
        store.reserve_call('alice', 'run1', 5, 5)

def test_real_unauthorized_never_calls_model(case, monkeypatch):
    monkeypatch.setattr('src.agent.extract_claim', lambda *args: pytest.fail('unauthorized API call'))
    result = run_agent(replace(case, mode='Real'), Settings(api_key='test', model='test'))
    assert result.result is None
    assert '登入' in result.error

def test_review_preserves_original_and_recalculates(case):
    result = run_agent(case, Settings())
    confirmed = review_case(result, '確認', '核對原文完成', Settings())
    assert confirmed.review_status == '已確認'
    assert result.reviews == ()
    corrected = review_case(confirmed, '修正', '重新核對', Settings(), result.extraction.claim)
    assert corrected.result.fund_waci == Decimal('50')
    assert corrected.run_id != confirmed.run_id
    assert len(corrected.reviews) == 2
    assert review_case(corrected, '退回', '請補資料', Settings()).review_status == '已退回'
    with pytest.raises(ValueError):
        review_case(result, '確認', '', Settings())

def test_authentication():
    users = {'alice': sha256(b'long-random-code').hexdigest()}
    assert authenticate('alice', 'long-random-code', users)
    assert not authenticate('bob', 'long-random-code', users)
    assert not authenticate('alice', '', users)


def test_model_function_arguments_are_validated(case, monkeypatch):
    from types import SimpleNamespace
    from src.claim_extraction import extract_claim, mock_claim, ExtractionError
    claim = mock_claim(case.claim).claim
    response = SimpleNamespace(status='completed', output=[SimpleNamespace(
        type='function_call', name='analyze_claim', arguments=claim.model_dump_json(), call_id='call-test')],
        usage=SimpleNamespace(input_tokens=50, output_tokens=20), _request_id='request-test')
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            assert kwargs['store'] is False
            assert kwargs['tools'][0]['strict'] is True
            assert kwargs['input'][1]['content'] == case.claim
            return response
    monkeypatch.setattr('src.claim_extraction.OpenAI', Client)
    result = extract_claim(case.claim, Settings(api_key='fake', model='fake'))
    assert result.tool_call_id == 'call-test'
    assert result.claim.reduction_pct == '30'
    response.output[0].arguments = '{}'
    with pytest.raises(ExtractionError):
        extract_claim(case.claim, Settings(api_key='fake', model='fake'))
