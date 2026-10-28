
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies.rbac import require_roles
from app.models.audit_log import AuditLog
from app.models.user import User
from app.routers.auth import get_db

router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"],
)


@router.get("/")
def get_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be between 1 and 100",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Offset cannot be negative",
        )

    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action)

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)

    total = query.count()

    records = (
        query.order_by(AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "audit_logs": [
            {
                "id": record.id,
                "user_id": record.user_id,
                "action": record.action,
                "entity_type": record.entity_type,
                "entity_id": record.entity_id,
                "details": record.details,
                "ip_address": record.ip_address,
                "created_at": record.created_at,
            }
            for record in records
        ],
    }
