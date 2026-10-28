import base64, hashlib, hmac, json, secrets, time
from ..config import settings

ITERATIONS = 310_000

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256": return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), int(rounds))
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
    except (ValueError, TypeError): return False

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def issue_token(username: str, name: str, role: str) -> tuple[str, int]:
    now=int(time.time()); expires=now+8*60*60
    payload=_b64(json.dumps({"sub":username,"name":name,"role":role,"exp":expires},separators=(",",":" )).encode())
    signature=_b64(hmac.new(settings.auth_secret.encode(),payload.encode(),hashlib.sha256).digest())
    return f"{payload}.{signature}", expires

def read_token(token: str | None) -> dict | None:
    if not token or "." not in token: return None
    try:
        payload, signature=token.split(".",1)
        expected=_b64(hmac.new(settings.auth_secret.encode(),payload.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(signature,expected): return None
        body=json.loads(base64.urlsafe_b64decode(payload+"="*(-len(payload)%4)))
        if body.get("exp",0)<int(time.time()) or not body.get("sub"): return None
        return body
    except (ValueError, TypeError, json.JSONDecodeError): return None
