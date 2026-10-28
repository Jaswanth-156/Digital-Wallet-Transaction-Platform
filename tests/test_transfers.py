
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
    Transfer,
    Transaction,
    TransactionLedger,
)
from app.models.idempotency_key import IdempotencyKey
from app.routers.auth import get_current_user
from app.routers.transfers import get_db as transfer_get_db


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

    sender_user = User(
        full_name="Test Sender",
        email="sender@test.com",
        hashed_password="test-password-hash",
        role_id=role.id,
    )

    receiver_user = User(
        full_name="Test Receiver",
        email="receiver@test.com",
        hashed_password="test-password-hash",
        role_id=role.id,
    )

    test_db.add_all([sender_user, receiver_user])
    test_db.flush()

    sender_wallet = Wallet(
        user_id=sender_user.id,
        currency="INR",
        status="ACTIVE",
    )

    receiver_wallet = Wallet(
        user_id=receiver_user.id,
        currency="INR",
        status="ACTIVE",
    )

    test_db.add_all([sender_wallet, receiver_wallet])
    test_db.flush()

    test_db.add_all(
        [
            WalletBalance(
                wallet_id=sender_wallet.id,
                available_balance=Decimal("100.00"),
                pending_balance=Decimal("0.00"),
            ),
            WalletBalance(
                wallet_id=receiver_wallet.id,
                available_balance=Decimal("20.00"),
                pending_balance=Decimal("0.00"),
            ),
        ]
    )

    test_db.commit()

    def override_get_db():
        yield test_db

    app.dependency_overrides[transfer_get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: sender_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_transfer_success(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "30.00",
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["status"] == "COMPLETED"
    assert data["amount"] == "30.00"
    assert data["sender_balance"] == "70.00"
    assert data["receiver_balance"] == "50.00"

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("70.00")
    assert receiver_balance.available_balance == Decimal("50.00")

    assert test_db.query(Transfer).count() == 1
    assert test_db.query(Transaction).count() == 2
    assert test_db.query(TransactionLedger).count() == 2


def test_transfer_insufficient_balance(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "150.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient wallet balance"

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("100.00")
    assert receiver_balance.available_balance == Decimal("20.00")

    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


def test_transfer_to_same_wallet(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": sender_wallet.id,
            "amount": "10.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot transfer to the same wallet"

    balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    assert balance.available_balance == Decimal("100.00")
    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


def test_transfer_from_frozen_wallet(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    sender_wallet.status = "FROZEN"
    test_db.commit()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "10.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Wallet is not active"

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("100.00")
    assert receiver_balance.available_balance == Decimal("20.00")

    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


def test_transfer_to_frozen_wallet(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    receiver_wallet.status = "FROZEN"
    test_db.commit()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "10.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Wallet is not active"

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("100.00")
    assert receiver_balance.available_balance == Decimal("20.00")

    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


def test_transfer_with_different_currencies(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    receiver_wallet.currency = "USD"
    test_db.commit()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "10.00",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Wallet currencies must match"

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("100.00")
    assert receiver_balance.available_balance == Decimal("20.00")

    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


@pytest.mark.parametrize("amount", ["0", "-10.00"])
def test_transfer_invalid_amount(client, test_db, amount):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": amount,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Transfer amount must be greater than zero"

    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


def test_transfer_from_another_users_wallet(client, test_db):
    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": receiver_wallet.id,
            "receiver_wallet_id": sender_wallet.id,
            "amount": "10.00",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Sender wallet not found"

    assert test_db.query(Transfer).count() == 0
    assert test_db.query(Transaction).count() == 0
    assert test_db.query(TransactionLedger).count() == 0


def test_sender_can_view_transfer_history(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    transfer = Transfer(
        sender_wallet_id=sender_wallet.id,
        receiver_wallet_id=receiver_wallet.id,
        amount=Decimal("10.00"),
        currency="INR",
        status="COMPLETED",
        reference_number="TEST-SENDER-HISTORY",
    )

    test_db.add(transfer)
    test_db.commit()

    response = client.get("/transfers/me")

    assert response.status_code == 200

    data = response.json()
    transfers = data["transfers"]

    assert data["total"] == 1
    assert len(transfers) == 1
    assert transfers[0]["reference_number"] == "TEST-SENDER-HISTORY"


def test_receiver_can_view_received_transfers(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    transfer = Transfer(
        sender_wallet_id=sender_wallet.id,
        receiver_wallet_id=receiver_wallet.id,
        amount=Decimal("10.00"),
        currency="INR",
        status="COMPLETED",
        reference_number="TEST-RECEIVER-HISTORY",
    )

    test_db.add(transfer)
    test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: receiver_user

    try:
        response = client.get("/transfers/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200

    data = response.json()
    transfers = data["transfers"]

    assert data["total"] == 1
    assert len(transfers) == 1
    assert transfers[0]["reference_number"] == "TEST-RECEIVER-HISTORY"


def test_user_cannot_view_unrelated_transfers(client, test_db):
    role = test_db.query(Role).first()

    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    unrelated_user = User(
        full_name="Unrelated User",
        email="unrelated@test.com",
        hashed_password="test-password-hash",
        role_id=role.id,
    )

    test_db.add(unrelated_user)
    test_db.flush()

    unrelated_wallet = Wallet(
        user_id=unrelated_user.id,
        currency="INR",
        status="ACTIVE",
    )

    test_db.add(unrelated_wallet)
    test_db.flush()

    transfer = Transfer(
        sender_wallet_id=sender_wallet.id,
        receiver_wallet_id=receiver_wallet.id,
        amount=Decimal("10.00"),
        currency="INR",
        status="COMPLETED",
        reference_number="TEST-UNRELATED-HISTORY",
    )

    test_db.add(transfer)
    test_db.commit()

    app.dependency_overrides[get_current_user] = lambda: unrelated_user

    try:
        response = client.get("/transfers/me")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 0
    assert data["transfers"] == []


def test_transfer_idempotency_prevents_duplicate_transfer(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    headers = {"Idempotency-Key": "transfer-test-key-001"}
    params = {
        "sender_wallet_id": sender_wallet.id,
        "receiver_wallet_id": receiver_wallet.id,
        "amount": "30.00",
    }

    first_response = client.post(
        "/transfers/",
        params=params,
        headers=headers,
    )

    second_response = client.post(
        "/transfers/",
        params=params,
        headers=headers,
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    assert first_response.json() == second_response.json()

    assert test_db.query(Transfer).count() == 1
    assert test_db.query(Transaction).count() == 2
    assert test_db.query(TransactionLedger).count() == 2
    assert test_db.query(IdempotencyKey).count() == 1

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("70.00")
    assert receiver_balance.available_balance == Decimal("50.00")


def test_transfer_idempotency_rejects_different_request(client, test_db):
    sender_user = test_db.query(User).filter(
        User.email == "sender@test.com"
    ).first()

    receiver_user = test_db.query(User).filter(
        User.email == "receiver@test.com"
    ).first()

    sender_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == sender_user.id
    ).first()

    receiver_wallet = test_db.query(Wallet).filter(
        Wallet.user_id == receiver_user.id
    ).first()

    headers = {"Idempotency-Key": "transfer-test-key-002"}

    first_response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "30.00",
        },
        headers=headers,
    )

    second_response = client.post(
        "/transfers/",
        params={
            "sender_wallet_id": sender_wallet.id,
            "receiver_wallet_id": receiver_wallet.id,
            "amount": "40.00",
        },
        headers=headers,
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 409

    assert second_response.json()["detail"] == (
        "Idempotency key was already used for a different request"
    )

    assert test_db.query(Transfer).count() == 1
    assert test_db.query(Transaction).count() == 2
    assert test_db.query(TransactionLedger).count() == 2
    assert test_db.query(IdempotencyKey).count() == 1

    sender_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == sender_wallet.id
    ).first()

    receiver_balance = test_db.query(WalletBalance).filter(
        WalletBalance.wallet_id == receiver_wallet.id
    ).first()

    assert sender_balance.available_balance == Decimal("70.00")
    assert receiver_balance.available_balance == Decimal("50.00")
