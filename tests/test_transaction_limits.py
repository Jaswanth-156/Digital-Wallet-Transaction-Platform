
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base
from app.models.role import Role
from app.models.user import User
from app.models.transaction_limit import TransactionLimit
from app.models.transaction_ledger import TransactionLedger
from app.routers.auth import get_db, get_current_user
from app.services.transaction_limit_service import validate_transaction_limit


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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_test_user(db, role_name, email):
    role = db.query(Role).filter(Role.name == role_name).first()

    if role is None:
        role = Role(name=role_name)
        db.add(role)
        db.commit()
        db.refresh(role)

    user = User(
        full_name="Test User",
        email=email,
        hashed_password="test-password-hash",
        role_id=role.id,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def setup_database():
    Base.metadata.create_all(bind=engine)


def teardown_database():
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_admin_create_transaction_limit():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-limits@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        with TestClient(app) as client:
            response = client.post(
                "/transaction-limits/",
                json={
                    "transaction_type": "DEPOSIT",
                    "minimum_amount": 100,
                    "maximum_amount": 10000,
                    "daily_limit": 50000,
                    "is_active": True,
                },
            )

            assert response.status_code in (200, 201), response.text
            assert response.json()["transaction_type"] == "DEPOSIT"
    finally:
        db.close()
        teardown_database()


def test_create_transaction_limit_invalid_type():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-invalid@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        with TestClient(app) as client:
            response = client.post(
                "/transaction-limits/",
                json={
                    "transaction_type": "invalid_type",
                    "minimum_amount": 100,
                    "maximum_amount": 10000,
                    "daily_limit": 50000,
                    "is_active": True,
                },
            )

            assert response.status_code in (400, 422), response.text
    finally:
        db.close()
        teardown_database()


def test_create_transaction_limit_invalid_amounts():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-amounts@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        with TestClient(app) as client:
            response = client.post(
                "/transaction-limits/",
                json={
                    "transaction_type": "DEPOSIT",
                    "minimum_amount": 10000,
                    "maximum_amount": 100,
                    "daily_limit": 50000,
                    "is_active": True,
                },
            )

            assert response.status_code in (400, 422), response.text
    finally:
        db.close()
        teardown_database()


def test_create_duplicate_transaction_limit():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-duplicate@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        payload = {
            "transaction_type": "DEPOSIT",
            "minimum_amount": 100,
            "maximum_amount": 10000,
            "daily_limit": 50000,
            "is_active": True,
        }

        with TestClient(app) as client:
            first_response = client.post(
                "/transaction-limits/",
                json=payload,
            )

            assert first_response.status_code in (200, 201), (
                first_response.text
            )

            second_response = client.post(
                "/transaction-limits/",
                json=payload,
            )

            assert second_response.status_code in (400, 409, 422), (
                second_response.text
            )
    finally:
        db.close()
        teardown_database()


def test_admin_list_transaction_limits():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-list@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        with TestClient(app) as client:
            response = client.get("/transaction-limits/")

            assert response.status_code == 200, response.text
            assert isinstance(response.json(), list)
    finally:
        db.close()
        teardown_database()


def test_admin_update_transaction_limit():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-update@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        with TestClient(app) as client:
            create_response = client.post(
                "/transaction-limits/",
                json={
                    "transaction_type": "DEPOSIT",
                    "minimum_amount": 100,
                    "maximum_amount": 10000,
                    "daily_limit": 50000,
                    "is_active": True,
                },
            )

            assert create_response.status_code in (200, 201), (
                create_response.text
            )

            limit_id = create_response.json()["id"]

            update_response = client.patch(
                f"/transaction-limits/{limit_id}",
                json={"maximum_amount": 20000},
            )

            assert update_response.status_code == 200, update_response.text
            assert Decimal(
                str(update_response.json()["maximum_amount"])
            ) == Decimal("20000")
    finally:
        db.close()
        teardown_database()


def test_update_nonexistent_transaction_limit():
    setup_database()
    db = TestingSessionLocal()

    try:
        admin = create_test_user(db, "Admin", "admin-missing@test.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin

        with TestClient(app) as client:
            response = client.patch(
                "/transaction-limits/999999",
                json={"maximum_amount": 20000},
            )

            assert response.status_code == 404, response.text
    finally:
        db.close()
        teardown_database()


def test_customer_cannot_access_transaction_limits():
    setup_database()
    db = TestingSessionLocal()

    try:
        customer = create_test_user(
            db,
            "Customer",
            "customer-limits@test.com",
        )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: customer

        with TestClient(app) as client:
            response = client.get("/transaction-limits/")

            assert response.status_code == 403, response.text
    finally:
        db.close()
        teardown_database()


def test_transaction_limit_rejects_amount_below_minimum():
    setup_database()
    db = TestingSessionLocal()

    try:
        db.add(
            TransactionLimit(
                transaction_type="DEPOSIT",
                minimum_amount=Decimal("100"),
                maximum_amount=Decimal("10000"),
                daily_limit=Decimal("50000"),
                is_active=True,
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as exc:
            validate_transaction_limit(
                db=db,
                transaction_type="DEPOSIT",
                amount=Decimal("50"),
                wallet_id=1,
            )

        assert exc.value.status_code == 400
        assert "minimum" in exc.value.detail.lower()
    finally:
        db.close()
        teardown_database()


def test_transaction_limit_rejects_amount_above_maximum():
    setup_database()
    db = TestingSessionLocal()

    try:
        db.add(
            TransactionLimit(
                transaction_type="DEPOSIT",
                minimum_amount=Decimal("100"),
                maximum_amount=Decimal("10000"),
                daily_limit=Decimal("50000"),
                is_active=True,
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as exc:
            validate_transaction_limit(
                db=db,
                transaction_type="DEPOSIT",
                amount=Decimal("15000"),
                wallet_id=1,
            )

        assert exc.value.status_code == 400
        assert "maximum" in exc.value.detail.lower()
    finally:
        db.close()
        teardown_database()


def test_transaction_limit_rejects_daily_limit_exceeded():
    setup_database()
    db = TestingSessionLocal()

    try:
        db.add(
            TransactionLimit(
                transaction_type="DEPOSIT",
                minimum_amount=Decimal("100"),
                maximum_amount=Decimal("10000"),
                daily_limit=Decimal("500"),
                is_active=True,
            )
        )
        db.commit()

        db.add(
            TransactionLedger(
                wallet_id=1,
                transaction_type="DEPOSIT",
                amount=Decimal("400"),
                balance_before=Decimal("1000"),
                balance_after=Decimal("1400"),
                reference_entity="DEPOSIT",
                reference_id=1,
                description="Deposit completed",
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as exc:
            validate_transaction_limit(
                db=db,
                transaction_type="DEPOSIT",
                amount=Decimal("200"),
                wallet_id=1,
            )

        assert exc.value.status_code == 400
        assert "daily" in exc.value.detail.lower()
    finally:
        db.close()
        teardown_database()


def test_transaction_limit_allows_amount_within_limits():
    setup_database()
    db = TestingSessionLocal()

    try:
        db.add(
            TransactionLimit(
                transaction_type="DEPOSIT",
                minimum_amount=Decimal("100"),
                maximum_amount=Decimal("10000"),
                daily_limit=Decimal("50000"),
                is_active=True,
            )
        )
        db.commit()

        validate_transaction_limit(
            db=db,
            transaction_type="DEPOSIT",
            amount=Decimal("500"),
            wallet_id=1,
        )
    finally:
        db.close()
        teardown_database()
