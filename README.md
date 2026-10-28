# Digital Wallet Transaction Platform

## 1. Project Overview

The Digital Wallet Transaction Platform is a backend application developed using FastAPI and PostgreSQL. It provides secure wallet management and financial transaction operations through REST APIs.

## 2. Technologies Used

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy ORM
- Alembic
- JWT Authentication
- Pydantic
- Pytest
- Uvicorn

## 3. Features

- User registration and login
- JWT access and refresh token authentication
- Logout and password change
- Wallet creation and balance management
- Deposits and withdrawals
- Wallet-to-wallet transfers
- Transaction history
- Refund management
- Transaction limits
- Suspicious transaction detection
- Notifications
- Audit logging
- Database migrations
- API documentation using Swagger UI

## 4. Project Structure

```text
Digital_Wallet_Transaction_Platform/
├── app/
│   ├── core/
│   ├── db/
│   ├── dependencies/
│   ├── models/
│   ├── repositories/
│   ├── routers/
│   ├── schemas/
│   └── services/
├── migrations/
├── tests/
├── alembic.ini
├── requirements.txt
└── README.md
```

## 5. Setup Instructions

### Prerequisites

- Python
- PostgreSQL
- pip

### Create and activate the virtual environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure the database

Configure the PostgreSQL connection and required application settings using your project's existing configuration and environment variables.

Do not commit real database passwords or secret keys.

### Run database migrations

```bash
alembic upgrade head
```

### Start the application

```bash
uvicorn app.main:app --reload
```

## 6. API Documentation

After starting the application, open:

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI Schema: http://127.0.0.1:8000/openapi.json

## 7. Run Automated Tests

Run the following command from the project root:

```bash
python -m pytest -v
```

The current test run completed successfully with **70 passed tests**.

## 8. Database Migrations

Alembic is used to manage database schema changes.

To check the current migration:

```bash
alembic current
```

## 9. Security

- Password hashing
- JWT-based authentication
- Access token validation
- Refresh token handling
- Active-user verification
- Wallet ownership checks
- Transaction amount and limit validation
- Audit logging

## 10. Project Status

The application starts successfully, Swagger documentation is accessible, and the automated test suite passes.
