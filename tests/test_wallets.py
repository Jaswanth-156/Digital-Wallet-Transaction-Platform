
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
    Transaction,
)
from app.routers.auth import get_current_user, get_db


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
        full_name="Wallet Customer",
        email="wallet@test.com",
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
            pending_balance=Decimal("10.00"),
        )
    )
    test_db.commit()

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_get_my_wallets(client, test_db):
    response = client.get("/wallets/me")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["currency"] == "INR"


def test_create_wallet_success(client, test_db):
    # The test fixture already creates an INR wallet.
    # Use a second customer to test wallet creation.
    role = test_db.query(Role).first()
    another_user = User(
        full_name="Second Customer",
        email="wallet2@test.com",
        hashed_password="test-password-hash",
        role_id=role.id,
    )
    test_db.add(another_user)
    test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: another_user

    response = client.post("/wallets/")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user_id"] == another_user.id
    assert data["currency"] == "INR"
    assert data["status"] == "ACTIVE"
    assert data["available_balance"] == "0.00"
    assert data["pending_balance"] == "0.00"

    balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == data["id"]
    ).first()
    assert balance is not None
    assert balance.available_balance == Decimal("0.00")


def test_create_duplicate_inr_wallet_rejected(client):
    response = client.post("/wallets/")

    assert response.status_code == 409
    assert response.json()["detail"] == "You already have an INR wallet"


def test_get_wallet_balance(client, test_db):
    wallet = test_db.query(Wallet).first()

    response = client.get(f"/wallets/{wallet.id}/balance")

    assert response.status_code == 200
    data = response.json()
    assert data["wallet_id"] == wallet.id
    assert data["currency"] == "INR"
    assert data["available_balance"] == "100.00"
    assert data["pending_balance"] == "10.00"


def test_cannot_view_another_users_wallet_balance(client, test_db):
    role = test_db.query(Role).first()
    another_user = User(
        full_name="Another Customer",
        email="wallet3@test.com",
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

    response = client.get(
        f"/wallets/{another_wallet.id}/balance"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Wallet not found"


def test_wallet_transactions_invalid_limit(client, test_db):
    wallet = test_db.query(Wallet).first()

    response = client.get(
        f"/wallets/{wallet.id}/transactions",
        params={"limit": 101},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Limit must be between 1 and 100"


def test_wallet_transactions_negative_offset(client, test_db):
    wallet = test_db.query(Wallet).first()

    response = client.get(
        f"/wallets/{wallet.id}/transactions",
        params={"offset": -1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Offset cannot be negative"


def test_wallet_transactions_empty_history(client, test_db):
    wallet = test_db.query(Wallet).first()

    response = client.get(f"/wallets/{wallet.id}/transactions")

    assert response.status_code == 200
    data = response.json()
    assert data["wallet_id"] == wallet.id
    assert data["total"] == 0
    assert data["transactions"] == []
