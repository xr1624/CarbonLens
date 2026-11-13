"""Generate a random demonstration access code and its server-side digest."""

from hashlib import sha256
import json
import secrets


if __name__ == "__main__":
    name = input("使用者名稱 > ").strip()
    if not name:
        raise SystemExit("請提供使用者名稱。")
    code = secrets.token_urlsafe(24)
    print("請將以下存取碼交給該使用者，並妥善保存")
    print(code)
    print("CARBONLENS_USERS_JSON 設定值")
    print(json.dumps({name: sha256(code.encode()).hexdigest()}, ensure_ascii=False))
