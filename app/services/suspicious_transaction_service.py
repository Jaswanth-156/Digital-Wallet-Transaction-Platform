
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.suspicious_transaction import SuspiciousTransaction
from app.models.transaction import Transaction


HIGH_RISK_AMOUNT = Decimal("20000.00")
CRITICAL_RISK_AMOUNT = Decimal("40000.00")


def check_suspicious_transaction(
    db: Session,
    transaction: Transaction,
) -> SuspiciousTransaction | None:
    amount = Decimal(str(transaction.amount))

    if amount >= CRITICAL_RISK_AMOUNT:
        risk_level = "CRITICAL"
        reason = (
            f"Transaction amount {amount} INR reached the critical "
            "risk threshold and requires security review."
        )
    elif amount >= HIGH_RISK_AMOUNT:
        risk_level = "HIGH"
        reason = (
            f"Transaction amount {amount} INR reached the high "
            "risk threshold and requires security review."
        )
    else:
        return None

    existing_record = (
        db.query(SuspiciousTransaction)
        .filter(
            SuspiciousTransaction.transaction_id == transaction.id
        )
        .first()
    )

    if existing_record:
        return existing_record

    suspicious_transaction = SuspiciousTransaction(
        transaction_id=transaction.id,
        reason=reason,
        risk_level=risk_level,
        status="PENDING",
    )

    db.add(suspicious_transaction)
    db.flush()

    return suspicious_transaction
