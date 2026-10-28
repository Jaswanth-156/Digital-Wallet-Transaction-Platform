
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet
from app.models.transaction import Transaction
from app.models.suspicious_transaction import SuspiciousTransaction
from app.services.suspicious_transaction_service import (
    check_suspicious_transaction,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_transaction(db, amount):
    role = Role(name="Customer")
    db.add(role)
    db.flush()

    user = User(
        full_name="Test Customer",
        email="test@example.com",
        hashed_password="test-password",
        role_id=role.id,
    )
    db.add(user)
    db.flush()

    wallet = Wallet(
        user_id=user.id,
        currency="INR",
        status="ACTIVE",
    )
    db.add(wallet)
    db.flush()

    transaction = Transaction(
        wallet_id=wallet.id,
        transaction_type="DEPOSIT",
        amount=Decimal(str(amount)),
        currency="INR",
        status="COMPLETED",
        reference_number=f"TEST-{amount}",
    )
    db.add(transaction)
    db.flush()

    return transaction


def test_amount_below_threshold_is_not_flagged(db):
    transaction = create_transaction(db, "19999.99")

    result = check_suspicious_transaction(db, transaction)

    assert result is None


def test_high_risk_amount_is_flagged(db):
    transaction = create_transaction(db, "20000.00")

    result = check_suspicious_transaction(db, transaction)

    assert result is not None
    assert result.risk_level == "HIGH"
    assert result.status == "PENDING"


def test_critical_risk_amount_is_flagged(db):
    transaction = create_transaction(db, "40000.00")

    result = check_suspicious_transaction(db, transaction)

    assert result is not None
    assert result.risk_level == "CRITICAL"
    assert result.status == "PENDING"


def test_existing_suspicious_record_is_not_duplicated(db):
    transaction = create_transaction(db, "25000.00")

    first = check_suspicious_transaction(db, transaction)
    db.flush()

    second = check_suspicious_transaction(db, transaction)

    assert first is not None
    assert second is not None
    assert first.id == second.id

    count = (
        db.query(SuspiciousTransaction)
        .filter(
            SuspiciousTransaction.transaction_id == transaction.id
        )
        .count()
    )

    assert count == 1
