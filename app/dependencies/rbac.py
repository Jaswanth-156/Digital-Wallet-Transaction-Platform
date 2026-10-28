
from fastapi import Depends, HTTPException, status

from app.models.user import User
from app.routers.auth import get_current_user


def require_roles(*allowed_roles: str):
    def check_role(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )

        return current_user

    return check_role
