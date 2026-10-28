from decimal import Decimal

from pydantic import BaseModel, Field


class RefundCreate(BaseModel):
    transaction_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class RefundResponse(BaseModel):
    id: int
    transaction_id: int
    wallet_id: int
    amount: Decimal
    status: str
    reference_number: str