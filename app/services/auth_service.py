
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest


def register_user(
    db: Session,
    user_data: RegisterRequest,
) -> User:
    existing_user = (
        db.query(User)
        .filter(User.email == str(user_data.email))
        .first()
    )

    if existing_user:
        raise ValueError("Email is already registered")

    customer_role = (
        db.query(Role)
        .filter(Role.name == "Customer")
        .first()
    )

    if customer_role is None:
        raise ValueError("Customer role is not configured")

    user = User(
        full_name=user_data.full_name,
        email=str(user_data.email),
        hashed_password=hash_password(user_data.password),
        role_id=customer_role.id,
        is_active=True,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise

    return user


def login_user(
    db: Session,
    user_data: LoginRequest,
) -> dict:
    user = (
        db.query(User)
        .filter(User.email == str(user_data.email))
        .first()
    )

    if user is None or not verify_password(
        user_data.password,
        user.hashed_password,
    ):
        raise ValueError("Invalid email or password")

    if not user.is_active:
        raise ValueError("User account is inactive")

    now = datetime.now(timezone.utc)

    access_token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.name,
            "iat": now,
            "exp": now + timedelta(
                minutes=settings.access_token_expire_minutes
            ),
            "type": "access",
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    refresh_token = secrets.token_urlsafe(48)
    refresh_token_hash = hashlib.sha256(
        refresh_token.encode("utf-8")
    ).hexdigest()

    stored_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=refresh_token_hash,
        expires_at=now + timedelta(days=7),
        is_revoked=False,
    )

    try:
        db.add(stored_refresh_token)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def refresh_access_token(
    db: Session,
    refresh_token: str,
) -> dict:
    token_hash = hashlib.sha256(
        refresh_token.encode("utf-8")
    ).hexdigest()

    stored_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .first()
    )

    now = datetime.now(timezone.utc)

    if stored_token is None:
        raise ValueError("Invalid or expired refresh token")

    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if stored_token.is_revoked or expires_at <= now:
        raise ValueError("Invalid or expired refresh token")

    user = db.query(User).filter(
        User.id == stored_token.user_id
    ).first()

    if user is None or not user.is_active:
        raise ValueError("User account is inactive")

    new_refresh_token = secrets.token_urlsafe(48)
    new_refresh_hash = hashlib.sha256(
        new_refresh_token.encode("utf-8")
    ).hexdigest()

    access_token = jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.name,
            "iat": now,
            "exp": now + timedelta(
                minutes=settings.access_token_expire_minutes
            ),
            "type": "access",
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    try:
        stored_token.is_revoked = True

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=new_refresh_hash,
                expires_at=now + timedelta(days=7),
                is_revoked=False,
            )
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


def logout_user(
    db: Session,
    refresh_token: str,
) -> None:
    token_hash = hashlib.sha256(
        refresh_token.encode("utf-8")
    ).hexdigest()

    stored_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )

    if stored_token is None or stored_token.is_revoked:
        raise ValueError("Invalid or already revoked refresh token")

    try:
        stored_token.is_revoked = True
        db.commit()
    except Exception:
        db.rollback()
        raise


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise ValueError("Current password is incorrect")

    if current_password == new_password:
        raise ValueError("New password must be different")

    try:
        user.hashed_password = hash_password(new_password)

        db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.is_revoked.is_(False),
        ).update(
            {"is_revoked": True},
            synchronize_session=False,
        )

        db.commit()
    except Exception:
        db.rollback()
        raise
