"""Versioned case records and explicit JSON serialization."""

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

import pandas as pd

from src.calculations import AnalysisResult, AnalysisStatus, HoldingContribution
from src.claim_extraction import Claim, Extraction
from src.validation import Benchmark, Fund, Holding, Issue, ValidationResult


def now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Event:
    tool: str
    status: str
    detail: str
    at: datetime = field(default_factory=now)


@dataclass(frozen=True)
class Review:
    action: str
    comment: str
    original: dict
    corrected: dict
    run_id: str
    at: datetime = field(default_factory=now)


@dataclass(frozen=True)
class Case:
    case_id: str
    fund_id: str
    fund_name: str
    source: str
    claim: str
    created_at: datetime
    result: AnalysisResult | None
    snapshot: dict = field(default_factory=dict)
    mode: str = "人工輸入"
    extraction: Extraction | None = None
    events: tuple[Event, ...] = ()
    claim_issues: tuple[str, ...] = ()
    error: str = ""
    review_status: str = "待人工覆核"
    reviews: tuple[Review, ...] = ()
    run_id: str = field(default_factory=lambda: uuid4().hex)
    revision: int = 0

    @property
    def status(self) -> str:
        return self.result.status.value if self.result else "執行失敗"


def snapshot_tables(tables: dict[str, pd.DataFrame]) -> dict:
    return {
        kind: {"records": frame.to_dict("records"), "columns": list(frame.columns),
               "source_file": frame.attrs.get("source_file", f"{kind}.csv"),
               "row_numbers": [frame.attrs.get("row_numbers", {}).get(index, position)
                               for position, index in enumerate(frame.index, 2)]}
        for kind, frame in tables.items()
    }


def restore_tables(snapshot: dict) -> dict[str, pd.DataFrame]:
    tables = {}
    for kind, data in snapshot.items():
        frame = pd.DataFrame.from_records(data["records"], columns=data["columns"])
        frame.attrs = {
            "source_file": data["source_file"],
            "row_numbers": dict(zip(frame.index, data["row_numbers"])),
        }
        tables[kind] = frame
    return tables


TYPES = {cls.__name__: cls for cls in (
    Case, Event, Review, Extraction, AnalysisResult, HoldingContribution,
    Benchmark, Fund, Holding, Issue, ValidationResult,
)}


def _encode(value):
    if isinstance(value, AnalysisStatus):
        return {"__type__": "AnalysisStatus", "value": value.value}
    if isinstance(value, (Decimal, datetime)):
        return {"__type__": type(value).__name__, "value": str(value)}
    if isinstance(value, Claim):
        return {"__type__": "Claim", "value": value.model_dump()}
    if is_dataclass(value):
        return {"__type__": type(value).__name__,
                "value": {item.name: _encode(getattr(value, item.name)) for item in fields(value)}}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "value": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value):
    kind = value.get("__type__")
    data = value.get("value")
    if kind in TYPES:
        return TYPES[kind](**data)
    if kind == "Decimal":
        return Decimal(data)
    if kind == "datetime":
        return datetime.fromisoformat(data)
    if kind == "tuple":
        return tuple(data)
    if kind == "AnalysisStatus":
        return AnalysisStatus(data)
    if kind == "Claim":
        return Claim.model_validate(data)
    return value


def encode_case(case: Case) -> str:
    return json.dumps(_encode(case), ensure_ascii=False, allow_nan=False)


def decode_case(payload: str) -> Case:
    case = json.loads(payload, object_hook=_decode)
    if not isinstance(case, Case):
        raise ValueError("案件資料格式無效。")
    return case
