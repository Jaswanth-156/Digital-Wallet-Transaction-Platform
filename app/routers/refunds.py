
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.refund import RefundCreate
from app.services.refund_service import create_refund

router = APIRouter(prefix="/refunds", tags=["Refunds"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def request_refund(
    refund_data: RefundCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_refund(
        db=db,
        transaction_id=refund_data.transaction_id,
        amount=refund_data.amount,
        current_user=current_user,
    )
