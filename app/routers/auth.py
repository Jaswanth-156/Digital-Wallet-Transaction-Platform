
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
)
from app.services.audit_log_service import create_audit_log
from app.services.auth_service import (
    change_password as change_password_service,
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    user_data: RegisterRequest,
    db: Session = Depends(get_db),
):
    try:
        user = register_user(db, user_data)

        create_audit_log(
            db=db,
            user_id=user.id,
            action="USER_REGISTERED",
            entity_type="USER",
            entity_id=user.id,
            details={"email": user.email},
        )

        db.commit()
        db.refresh(user)

        return user

    except ValueError as exc:
        db.rollback()
        message = str(exc)

        if message == "Email is already registered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message,
            ) from exc

        if message == "Customer role is not configured":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration could not be completed",
        ) from exc

    except Exception:
        db.rollback()
        raise


@router.post("/login", response_model=LoginResponse)
def login(
    user_data: LoginRequest,
    db: Session = Depends(get_db),
):
    try:
        response = login_user(db, user_data)

        user = (
            db.query(User)
            .filter(User.email == str(user_data.email))
            .first()
        )

        if user is None:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        create_audit_log(
            db=db,
            user_id=user.id,
            action="USER_LOGIN",
            entity_type="USER",
            entity_id=user.id,
            details={"email": user.email},
        )

        db.commit()

        return response

    except ValueError as exc:
        db.rollback()

        if str(exc) == "User account is inactive":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    try:
        return refresh_access_token(db, token_data.refresh_token)

    except ValueError as exc:
        db.rollback()
        message = str(exc)

        if message == "User account is inactive":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc


@router.post("/logout")
def logout(
    token_data: LogoutRequest,
    db: Session = Depends(get_db),
):
    try:
        token_hash = __import__("hashlib").sha256(
            token_data.refresh_token.encode("utf-8")
        ).hexdigest()

        stored_token = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )

        if stored_token is None or stored_token.is_revoked:
            raise ValueError("Invalid or already revoked refresh token")

        user_id = stored_token.user_id

        logout_user(db, token_data.refresh_token)

        create_audit_log(
            db=db,
            user_id=user_id,
            action="USER_LOGOUT",
            entity_type="AUTHENTICATION",
            entity_id=user_id,
            details={"event": "Refresh token revoked"},
        )

        db.commit()

        return {"message": "Logged out successfully"}

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or already revoked refresh token",
        ) from exc

    except Exception:
        db.rollback()
        raise


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.post("/change-password")
def change_password(
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        change_password_service(
            db=db,
            user=current_user,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
        )

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="PASSWORD_CHANGED",
            entity_type="USER",
            entity_id=current_user.id,
            details={"event": "Password changed successfully"},
        )

        db.commit()

        return {"message": "Password changed successfully"}

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception:
        db.rollback()
        raise
