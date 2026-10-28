
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.models.transaction_limit import TransactionLimit
from app.routers.auth import get_db, get_current_user


router = APIRouter(
    prefix="/transaction-limits",
    tags=["Transaction Limits"],
)


class TransactionLimitCreate(BaseModel):
    transaction_type: Literal[
        "DEPOSIT",
        "WITHDRAWAL",
        "TRANSFER",
        "REFUND",
    ]
    minimum_amount: Decimal = Field(gt=0)
    maximum_amount: Decimal = Field(gt=0)
    daily_limit: Decimal = Field(gt=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.maximum_amount < self.minimum_amount:
            raise ValueError(
                "Maximum amount cannot be less than minimum amount"
            )

        if self.daily_limit < self.maximum_amount:
            raise ValueError(
                "Daily limit cannot be less than maximum amount"
            )

        return self


class TransactionLimitUpdate(BaseModel):
    minimum_amount: Decimal | None = Field(default=None, gt=0)
    maximum_amount: Decimal | None = Field(default=None, gt=0)
    daily_limit: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class TransactionLimitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_type: str
    minimum_amount: Decimal
    maximum_amount: Decimal
    daily_limit: Decimal
    is_active: bool


def require_admin(current_user):
    if (
        current_user.role is None
        or current_user.role.name.lower() != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage transaction limits",
        )


@router.post(
    "/",
    response_model=TransactionLimitResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction_limit(
    payload: TransactionLimitCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    transaction_type = payload.transaction_type.upper()

    existing_limit = (
        db.query(TransactionLimit)
        .filter(
            TransactionLimit.transaction_type == transaction_type
        )
        .first()
    )

    if existing_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A limit for this transaction type already exists",
        )

    transaction_limit = TransactionLimit(
        **{
            **payload.model_dump(),
            "transaction_type": transaction_type,
        }
    )

    db.add(transaction_limit)

    try:
        db.commit()
        db.refresh(transaction_limit)
    except Exception:
        db.rollback()
        raise

    return transaction_limit


@router.get(
    "/",
    response_model=list[TransactionLimitResponse],
)
def list_transaction_limits(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    return (
        db.query(TransactionLimit)
        .order_by(TransactionLimit.id)
        .all()
    )


@router.patch(
    "/{limit_id}",
    response_model=TransactionLimitResponse,
)
def update_transaction_limit(
    limit_id: int,
    payload: TransactionLimitUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    transaction_limit = (
        db.query(TransactionLimit)
        .filter(TransactionLimit.id == limit_id)
        .first()
    )

    if transaction_limit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction limit not found",
        )

    updates = payload.model_dump(exclude_unset=True)

    minimum_amount = updates.get(
        "minimum_amount",
        transaction_limit.minimum_amount,
    )
    maximum_amount = updates.get(
        "maximum_amount",
        transaction_limit.maximum_amount,
    )
    daily_limit = updates.get(
        "daily_limit",
        transaction_limit.daily_limit,
    )

    if minimum_amount is not None and maximum_amount is not None:
        if maximum_amount < minimum_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Maximum amount cannot be less than minimum amount"
                ),
            )

    if daily_limit is not None and maximum_amount is not None:
        if daily_limit < maximum_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Daily limit cannot be less than maximum amount"
                ),
            )

    for field, value in updates.items():
        setattr(transaction_limit, field, value)

    try:
        db.commit()
        db.refresh(transaction_limit)
    except Exception:
        db.rollback()
        raise

    return transaction_limit
