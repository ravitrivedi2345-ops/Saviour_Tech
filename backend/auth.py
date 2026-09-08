"""
auth.py — Authentication, Role-Based Access Control (RBAC), and Audit Logging.

Roles:
  - Admin: Full system control (configurations, user management, blacklist CRUD, audit logs)
  - Traffic Police: Trajectory searches, enforcement identity vault, alert status resolution, video upload, live map
  - City Planner: City traffic analytics dashboard, heatmaps, route densities, comparative trends (owner vault blocked)

Session:
  - JWT access tokens with 30-minute inactivity expiration
  - Refresh token support (7-day validity)
  - Audit logging for every login attempt and plate search query
"""

import os
import sys
import json
import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union, Any

from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(__file__))
from database import SessionLocal, UserRecord, AuthAuditRecord

# Type alias
User = UserRecord

# ─── Configuration ─────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "anpr-delhi-traffic-jwt-secret-key-2026-auth-token-super-secure")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ─── Password Hashing & Verification (Native Bcrypt) ──────────────────────────

def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pw_bytes = password.encode("utf-8")[:72]  # Bcrypt 72-byte max
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


hash_password = get_password_hash


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        h_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, h_bytes)
    except Exception as e:
        print(f"[Auth] Password verification error: {e}")
        return False


def authenticate_user(username: str, password: str) -> Optional[UserRecord]:
    """Authenticate a user by username and password against database."""
    session = SessionLocal()
    try:
        user = session.query(UserRecord).filter_by(username=username).first()
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login = datetime.now(timezone.utc)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


# ─── JWT Token Generation & Verification ──────────────────────────────────────

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "access",
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT refresh token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again or refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, Exception) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── Database Dependency ──────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Audit Trail Logger Helper ────────────────────────────────────────────────

def log_auth_audit(
    username: str,
    action: str,
    resource: Optional[str] = None,
    status: str = "SUCCESS",
    details: Optional[Dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    """
    Record an action in the immutable audit log table for legal compliance.
    Never blocks or raises exceptions.
    """
    should_close = False
    session = db
    if session is None:
        session = SessionLocal()
        should_close = True

    try:
        audit_rec = AuthAuditRecord(
            user_id=user_id,
            username=username,
            role=role,
            action=action,
            resource=resource,
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
            timestamp=datetime.now(timezone.utc),
        )
        session.add(audit_rec)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Audit Log Error]: Failed to write audit record: {e}")
    finally:
        if should_close:
            session.close()


# ─── Current User Dependency ──────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserRecord:
    """
    Extract, validate JWT, and return the authenticated UserRecord.
    Also accepts Authorization header from request directly.
    """
    auth_header = request.headers.get("Authorization")
    if not token and auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this resource.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — access token required.",
        )

    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject identifier.",
        )

    user = db.query(UserRecord).filter_by(username=username).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account does not exist or has been disabled.",
        )

    return user


# ─── Optional User (for endpoints that support both public & authenticated) ────

async def get_optional_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[UserRecord]:
    """Return UserRecord if authenticated, or None if anonymous."""
    try:
        return await get_current_user(request, token, db)
    except HTTPException:
        return None


# ─── RBAC Role Checker Dependency Factory ─────────────────────────────────────

def require_roles(allowed_roles: List[str]):
    """
    Dependency generator that verifies the current user has one of the allowed roles.
    Example: Depends(require_roles(["Admin", "Traffic Police"]))
    """
    async def role_checker(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied for role '{current_user.role}'. "
                    f"Required one of: {allowed_roles}"
                ),
            )
        return current_user

    return role_checker
