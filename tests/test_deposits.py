
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
    Deposit,
    Transaction,
    TransactionLedger,
)
from app.routers.auth import get_current_user
from app.routers.deposits import get_db as deposit_get_db


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
    role = Role(name="Customer", description="Test customer")
    test_db.add(role)
    test_db.flush()

    user = User(
        full_name="Test Customer",
        email="deposit@test.com",
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
            available_balance=Decimal("100.00"),
            pending_balance=Decimal("0.00"),
        )
    )
    test_db.commit()

    def override_get_db():
        yield test_db

    app.dependency_overrides[deposit_get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_create_deposit_success(client, test_db):
    wallet = test_db.query(Wallet).first()

    response = client.post(
        "/deposits/",
        params={"wallet_id": wallet.id, "amount": "20.00"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["wallet_id"] == wallet.id
    assert data["amount"] == "20.00"
    assert data["currency"] == "INR"
    assert data["status"] == "PENDING"
    assert data["reference_number"].startswith("DEP-")

    deposit = test_db.query(Deposit).first()
    assert deposit is not None
    assert deposit.status == "PENDING"


def test_create_deposit_rejects_zero_amount(client, test_db):
    wallet = test_db.query(Wallet).first()

    response = client.post(
        "/deposits/",
        params={"wallet_id": wallet.id, "amount": "0"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Deposit amount must be greater than zero"
    )
    assert test_db.query(Deposit).count() == 0


def test_create_deposit_rejects_another_users_wallet(client, test_db):
    role = test_db.query(Role).first()

    another_user = User(
        full_name="Another Customer",
        email="another-deposit@test.com",
        hashed_password="test-password-hash",
        role_id=role.id,
    )
    test_db.add(another_user)
    test_db.flush()

    another_wallet = Wallet(
        user_id=another_user.id,
        currency="INR",
        status="ACTIVE",
    )
    test_db.add(another_wallet)
    test_db.commit()

    response = client.post(
        "/deposits/",
        params={"wallet_id": another_wallet.id, "amount": "10.00"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"
    assert test_db.query(Deposit).count() == 0


def test_complete_deposit_success(client, test_db):
    wallet = test_db.query(Wallet).first()

    deposit = Deposit(
        wallet_id=wallet.id,
        amount=Decimal("20.00"),
        currency="INR",
        status="PENDING",
        reference_number="TEST-DEP-001",
    )
    test_db.add(deposit)
    test_db.commit()
    test_db.refresh(deposit)

    response = client.post(f"/deposits/{deposit.id}/complete")

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["deposit_id"] == deposit.id
    assert data["wallet_id"] == wallet.id
    assert data["amount"] == "20.00"
    assert data["status"] == "COMPLETED"
    assert data["available_balance"] == "120.00"

    balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == wallet.id
    ).first()
    assert balance.available_balance == Decimal("120.00")

    transaction = test_db.query(Transaction).filter(
        Transaction.reference_number == "TEST-DEP-001"
    ).first()
    assert transaction is not None
    assert transaction.transaction_type == "DEPOSIT"
    assert transaction.status == "COMPLETED"

    ledger = test_db.query(TransactionLedger).filter(
        TransactionLedger.reference_entity == "DEPOSIT",
        TransactionLedger.reference_id == deposit.id,
    ).first()
    assert ledger is not None
    assert ledger.balance_before == Decimal("100.00")
    assert ledger.balance_after == Decimal("120.00")


def test_complete_deposit_rejects_repeated_completion(client, test_db):
    wallet = test_db.query(Wallet).first()

    deposit = Deposit(
        wallet_id=wallet.id,
        amount=Decimal("20.00"),
        currency="INR",
        status="PENDING",
        reference_number="TEST-DEP-002",
    )
    test_db.add(deposit)
    test_db.commit()
    test_db.refresh(deposit)

    first_response = client.post(f"/deposits/{deposit.id}/complete")
    assert first_response.status_code == 200, first_response.text

    second_response = client.post(f"/deposits/{deposit.id}/complete")

    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Deposit is not pending"

    balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == wallet.id
    ).first()
    assert balance.available_balance == Decimal("120.00")

    assert test_db.query(Transaction).filter(
        Transaction.reference_number == "TEST-DEP-002"
    ).count() == 1
