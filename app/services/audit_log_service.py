
import json

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    action: str,
    entity_type: str,
    user_id: int | None = None,
    entity_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
):
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details) if details is not None else None,
        ip_address=ip_address,
    )

    db.add(audit_log)
    db.flush()

    return audit_log
