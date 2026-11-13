"""Server-side configuration, including deployment secrets."""

from dataclasses import dataclass
import json
import os
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    model: str = ""
    timeout: int = 30
    max_output_tokens: int = 1200
    max_claim_chars: int = 6000
    user_daily_calls: int = 10
    global_daily_calls: int = 100
    public: bool = True
    users_json: str = "{}"
    database_url: str = ""

    def users(self) -> dict[str, str]:
        users = json.loads(self.users_json)
        if not isinstance(users, dict) or any(
            not isinstance(name, str) or not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            for name, digest in users.items()
        ):
            raise ValueError("CARBONLENS_USERS_JSON 須為使用者名稱與 SHA256 摘要對照。")
        return users


def load_settings(secrets=None) -> Settings:
    values = {**dotenv_values(ROOT / ".env", encoding="utf-8-sig"), **os.environ}
    if secrets:
        values.update(dict(secrets))

    def integer(key, default, maximum):
        value = int(values.get(key, default))
        if not 1 <= value <= maximum:
            raise ValueError(f"{key} 超出允許範圍。")
        return value

    settings = Settings(
        api_key=str(values.get("OPENAI_API_KEY", "")),
        model=str(values.get("OPENAI_MODEL", "")),
        timeout=integer("OPENAI_TIMEOUT_SECONDS", 30, 120),
        max_output_tokens=integer("OPENAI_MAX_OUTPUT_TOKENS", 1200, 4096),
        max_claim_chars=integer("CARBONLENS_MAX_CLAIM_CHARS", 6000, 12000),
        user_daily_calls=integer("CARBONLENS_USER_DAILY_CALLS", 10, 1000),
        global_daily_calls=integer("CARBONLENS_GLOBAL_DAILY_CALLS", 100, 10000),
        public=str(values.get("CARBONLENS_PUBLIC", "true")).lower() == "true",
        users_json=str(values.get("CARBONLENS_USERS_JSON", "{}")),
        database_url=str(values.get("DATABASE_URL", "")),
    )
    settings.users()
    return settings
