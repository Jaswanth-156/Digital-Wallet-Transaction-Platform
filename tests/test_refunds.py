
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.main import app
from app.models import (
    Role,
    User,
    Wallet,
    WalletBalance,
    Refund,
    Transaction,
    TransactionLedger,
)
from app.routers.auth import get_current_user
from app.routers.refunds import get_db as refund_get_db


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
)


@pytest.fixture
def test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(test_db):
    role = Role(
        name="Customer",
        description="Test customer",
    )
    test_db.add(role)
    test_db.flush()

    user = User(
        full_name="Test Customer",
        email="customer@test.com",
        hashed_password="test-password-hash",
        role_id=role.id,
    )
    test_db.add(user)
    test_db.flush()

    wallet = Wallet(
        user_id=user.id,
        currency="INR",
        status="ACTIVE",
    )
    test_db.add(wallet)
    test_db.flush()

    test_db.add(
        WalletBalance(
            wallet_id=wallet.id,
            available_balance=Decimal("80.00"),
            pending_balance=Decimal("0.00"),
        )
    )

    original_transaction = Transaction(
        wallet_id=wallet.id,
        transaction_type="DEPOSIT",
        amount=Decimal("100.00"),
        currency="INR",
        status="COMPLETED",
        reference_number="TEST-DEPOSIT-001",
    )
    test_db.add(original_transaction)
    test_db.commit()

    def override_get_db():
        yield test_db

    app.dependency_overrides[refund_get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_refund_success(client, test_db):
    transaction = test_db.query(Transaction).filter(
        Transaction.reference_number == "TEST-DEPOSIT-001"
    ).first()

    response = client.post(
        "/refunds/",
        json={
            "transaction_id": transaction.id,
            "amount": "10.00",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["amount"] == "10.00"
    assert data["available_balance"] == "70.00"

    refund = test_db.query(Refund).filter(
        Refund.transaction_id == transaction.id
    ).first()
    assert refund is not None
    assert refund.status == "COMPLETED"

    refund_transaction = test_db.query(Transaction).filter(
        Transaction.reference_number == f"REF-TXN-{refund.id}"
    ).first()
    assert refund_transaction is not None
    assert refund_transaction.transaction_type == "REFUND"

    ledger = test_db.query(TransactionLedger).filter(
        TransactionLedger.reference_entity == "REFUND",
        TransactionLedger.reference_id == refund.id,
    ).first()
    assert ledger is not None
    assert ledger.balance_before == Decimal("80.00")
    assert ledger.balance_after == Decimal("70.00")


def test_refund_exceeds_original_amount(client, test_db):
    transaction = test_db.query(Transaction).filter(
        Transaction.reference_number == "TEST-DEPOSIT-001"
    ).first()

    response = client.post(
        "/refunds/",
        json={
            "transaction_id": transaction.id,
            "amount": "101.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Refund amount cannot exceed the original transaction amount"
    )

    assert test_db.query(Refund).count() == 0


def test_total_refunds_cannot_exceed_original_amount(client, test_db):
    transaction = test_db.query(Transaction).filter(
        Transaction.reference_number == "TEST-DEPOSIT-001"
    ).first()

    test_db.add(
        Refund(
            transaction_id=transaction.id,
            wallet_id=transaction.wallet_id,
            amount=Decimal("20.00"),
            status="COMPLETED",
            reference_number="TEST-REFUND-001",
        )
    )
    test_db.commit()

    response = client.post(
        "/refunds/",
        json={
            "transaction_id": transaction.id,
            "amount": "81.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Total refunds cannot exceed the original transaction amount"
    )


def test_refund_insufficient_balance(client, test_db):
    transaction = test_db.query(Transaction).filter(
        Transaction.reference_number == "TEST-DEPOSIT-001"
    ).first()

    response = client.post(
        "/refunds/",
        json={
            "transaction_id": transaction.id,
            "amount": "85.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Insufficient wallet balance for refund"
    )

    assert test_db.query(Refund).count() == 0

    balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == transaction.wallet_id
    ).first()
    assert balance.available_balance == Decimal("80.00")


def test_refund_rejects_invalid_transaction_id(client, test_db):
    response = client.post(
        "/refunds/",
        json={
            "transaction_id": 0,
            "amount": "10.00",
        },
    )

    assert response.status_code == 422
    assert test_db.query(Refund).count() == 0
