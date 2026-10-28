
from fastapi import Depends, FastAPI

from app.core.config import settings
from app.dependencies.rbac import require_roles
from app.models.user import User
from app.routers import audit_logs, auth, dashboard, suspicious_transactions, transaction_limits, wallets,deposits,withdrawals,transfers,refunds,notifications

app = FastAPI(title=settings.app_name)

app.include_router(auth.router)
app.include_router(wallets.router)
app.include_router(deposits.router)
app.include_router(withdrawals.router)
app.include_router(transfers.router)
app.include_router(refunds.router)
app.include_router(dashboard.router)
app.include_router(suspicious_transactions.router)
app.include_router(audit_logs.router)
app.include_router(transaction_limits.router)
app.include_router(notifications.router)