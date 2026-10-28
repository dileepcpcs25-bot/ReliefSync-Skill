"""Shared-key operator sign-in endpoints. This is not individual user authentication."""
import hmac

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..dependencies import DbSession, OperatorDep, RateLimiter, commit
from ..schemas_ext import AccountRegister, OperatorLogin, PasswordChange, PasswordLogin
from ..models import OperatorUser
from ..services.account_security import hash_password, issue_token, verify_password
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["Authentication"] )
_login_limit = RateLimiter("operator-login", 10)


@router.get("/config")
def auth_config(db: DbSession):
    admin = db.scalar(select(OperatorUser).where(OperatorUser.username == "admin", OperatorUser.active.is_(True)))
    demo_enabled = bool(admin and verify_password("ReliefSync-admin-2026!", admin.password_hash))
    return {"key_required": bool(settings.operator_api_key), "development_open_access": False,
            "password_auth_enabled": True, "registration_enabled": settings.allow_user_registration,
            "auth_type": "multi_user_password", "token_hours": 8,
            "demo_login": {"username": "admin", "password": "ReliefSync-admin-2026!"} if demo_enabled else None}


@router.post("/login", dependencies=[Depends(_login_limit)])
def operator_login(body: OperatorLogin):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Enter your name.")
    if settings.operator_api_key:
        if not body.key or not hmac.compare_digest(body.key.encode(), settings.operator_api_key.encode()):
            raise HTTPException(401, "The operator key is incorrect.")
        return {"authenticated": True, "name": name, "mode": "shared_key"}
    if settings.app_env == "production":
        raise HTTPException(503, "Operator access is not configured. Set OPERATOR_API_KEY on the backend.")
    return {"authenticated": True, "name": name, "mode": "development"}


@router.post("/register", status_code=201, dependencies=[Depends(_login_limit)])
def register_account(body: AccountRegister, db: DbSession):
    if not settings.allow_user_registration:
        raise HTTPException(403, "New account registration is disabled by the administrator.")
    username = body.username.lower()
    if db.scalar(select(OperatorUser.id).where(OperatorUser.username == username)):
        raise HTTPException(409, "That username is already registered.")
    user = OperatorUser(username=username, display_name=body.display_name.strip(), role="operator", password_hash=hash_password(body.password))
    db.add(user)
    commit(db, "That username is already registered.")
    token, expires = issue_token(user.username, user.display_name, user.role)
    return {"authenticated": True, "token": token, "expires_at": expires, "username": user.username, "name": user.display_name, "role": user.role}


@router.post("/login/password", dependencies=[Depends(_login_limit)])
def password_login(body: PasswordLogin, db: DbSession):
    user = db.scalar(select(OperatorUser).where(OperatorUser.username == body.username.lower(), OperatorUser.active.is_(True)))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Username or password is incorrect.")
    token, expires = issue_token(user.username, user.display_name, user.role)
    return {"authenticated": True, "token": token, "expires_at": expires, "username": user.username, "name": user.display_name, "role": user.role}


@router.get("/me")
def current_account(operator: OperatorDep):
    return {"name": operator.name, "role": operator.role}


@router.post("/change-password")
def change_password(body: PasswordChange, db: DbSession, operator: OperatorDep):
    user = db.scalar(select(OperatorUser).where(OperatorUser.username == operator.username, OperatorUser.active.is_(True)))
    if not user or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    commit(db)
    return {"updated": True}
