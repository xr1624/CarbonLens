"""Run one synthetic extraction without logging credentials."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settings import load_settings
from src.claim_extraction import extract_claim, check_claim, ExtractionError

settings = load_settings()
if not settings.api_key.strip():
    print('API_KEY_MISSING')
    raise SystemExit(1)
text = '本基金 2025 年的投資組合碳強度較 CarbonLens 合成市場基準低 30%。'
try:
    result = extract_claim(text, settings)
    target, problems = check_claim(result.claim, text)
    print({'model': result.model, 'target': str(target), 'validation_issues': len(problems),
           'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens,
           'request_id': result.request_id})
except ExtractionError as error:
    print(str(error))
    raise SystemExit(1)
