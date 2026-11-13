"""Prepare ignored deployment secrets without printing credentials."""
from pathlib import Path
from hashlib import sha256
import json
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settings import load_settings, ROOT

settings = load_settings()
directory = ROOT / 'runtime'
directory.mkdir(exist_ok=True)
access_file = directory / 'cloud-access.txt'
if not access_file.exists():
    access_file.write_text(secrets.token_urlsafe(32), encoding='utf-8')
code = access_file.read_text(encoding='utf-8').strip()
users = json.dumps({'xr1624': sha256(code.encode()).hexdigest()})
values = {
    'OPENAI_API_KEY': settings.api_key, 'OPENAI_MODEL': settings.model,
    'CARBONLENS_PUBLIC': 'true', 'CARBONLENS_USERS_JSON': users,
    'CARBONLENS_USER_DAILY_CALLS': 10, 'CARBONLENS_GLOBAL_DAILY_CALLS': 30,
    'OPENAI_MAX_OUTPUT_TOKENS': 1200, 'OPENAI_TIMEOUT_SECONDS': 30,
    'DATABASE_URL': settings.database_url,
}
(directory / 'cloud-secrets.toml').write_text(
    '\n'.join(f'{key} = {json.dumps(value, ensure_ascii=False)}' for key, value in values.items()) + '\n', encoding='utf-8')
print('Prepared ignored runtime/cloud-secrets.toml and runtime/cloud-access.txt')
