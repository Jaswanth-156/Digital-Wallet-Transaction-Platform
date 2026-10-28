
"""add model constraints and timestamps

Revision ID: abda02a0b6b6
Revises: cd431bf306cb
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "abda02a0b6b6"
down_revision: Union[str, Sequence[str], None] = "cd431bf306cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timestamps safely for existing rows.
    op.add_column(
        "audit_logs",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "notifications",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "refresh_tokens",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Wallet constraints
    op.create_check_constraint(
        "ck_wallet_status_valid",
        "wallets",
        "status IN ('ACTIVE', 'FROZEN', 'SUSPENDED', 'CLOSED')",
    )
    op.create_check_constraint(
        "ck_wallet_currency_uppercase",
        "wallets",
        "currency = upper(currency)",
    )

    # Wallet balance constraints
    op.create_check_constraint(
        "ck_wallet_available_balance_nonnegative",
        "wallet_balances",
        "available_balance >= 0",
    )
    op.create_check_constraint(
        "ck_wallet_pending_balance_nonnegative",
        "wallet_balances",
        "pending_balance >= 0",
    )

    # Deposit constraints
    op.create_check_constraint(
        "ck_deposit_amount_positive",
        "deposits",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_deposit_status_valid",
        "deposits",
        "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.create_check_constraint(
        "ck_deposit_currency_uppercase",
        "deposits",
        "currency = upper(currency)",
    )

    # Withdrawal constraints
    op.create_check_constraint(
        "ck_withdrawal_amount_positive",
        "withdrawals",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_withdrawal_status_valid",
        "withdrawals",
        "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.create_check_constraint(
        "ck_withdrawal_currency_uppercase",
        "withdrawals",
        "currency = upper(currency)",
    )

    # Transfer constraints
    op.create_check_constraint(
        "ck_transfer_amount_positive",
        "transfers",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_transfer_different_wallets",
        "transfers",
        "sender_wallet_id <> receiver_wallet_id",
    )
    op.create_check_constraint(
        "ck_transfer_status_valid",
        "transfers",
        "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.create_check_constraint(
        "ck_transfer_currency_uppercase",
        "transfers",
        "currency = upper(currency)",
    )

    # Transaction constraints
    op.create_check_constraint(
        "ck_transaction_amount_positive",
        "transactions",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_transaction_type_valid",
        "transactions",
        "transaction_type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'REFUND', 'FEE', 'ADJUSTMENT', 'REVERSAL')",
    )
    op.create_check_constraint(
        "ck_transaction_status_valid",
        "transactions",
        "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
    op.create_check_constraint(
        "ck_transaction_currency_uppercase",
        "transactions",
        "currency = upper(currency)",
    )

    # Ledger constraints
    op.create_check_constraint(
        "ck_ledger_amount_positive",
        "transaction_ledger",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_ledger_balance_before_nonnegative",
        "transaction_ledger",
        "balance_before >= 0",
    )
    op.create_check_constraint(
        "ck_ledger_balance_after_nonnegative",
        "transaction_ledger",
        "balance_after >= 0",
    )

    # Refund constraints
    op.create_check_constraint(
        "ck_refund_amount_positive",
        "refunds",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_refund_status_valid",
        "refunds",
        "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )

    # Transaction limit constraints
    op.create_check_constraint(
        "ck_transaction_limit_minimum_positive",
        "transaction_limits",
        "minimum_amount > 0",
    )
    op.create_check_constraint(
        "ck_transaction_limit_maximum_gte_minimum",
        "transaction_limits",
        "maximum_amount >= minimum_amount",
    )
    op.create_check_constraint(
        "ck_transaction_limit_daily_positive",
        "transaction_limits",
        "daily_limit > 0",
    )
    op.create_check_constraint(
        "ck_transaction_limit_type_valid",
        "transaction_limits",
        "transaction_type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'REFUND')",
    )

    # Suspicious transaction constraints
    op.create_check_constraint(
        "ck_suspicious_transaction_risk_level_valid",
        "suspicious_transactions",
        "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
    )
    op.create_check_constraint(
        "ck_suspicious_transaction_status_valid",
        "suspicious_transactions",
        "status IN ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED')",
    )

    # Notification constraint
    op.create_check_constraint(
        "ck_notification_type_valid",
        "notifications",
        "notification_type IN ('TRANSACTION', 'SECURITY', 'ACCOUNT', 'SYSTEM')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_notification_type_valid",
        "notifications",
        type_="check",
    )

    op.drop_constraint(
        "ck_suspicious_transaction_status_valid",
        "suspicious_transactions",
        type_="check",
    )
    op.drop_constraint(
        "ck_suspicious_transaction_risk_level_valid",
        "suspicious_transactions",
        type_="check",
    )

    op.drop_constraint(
        "ck_transaction_limit_type_valid",
        "transaction_limits",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_limit_daily_positive",
        "transaction_limits",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_limit_maximum_gte_minimum",
        "transaction_limits",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_limit_minimum_positive",
        "transaction_limits",
        type_="check",
    )

    op.drop_constraint(
        "ck_refund_status_valid",
        "refunds",
        type_="check",
    )
    op.drop_constraint(
        "ck_refund_amount_positive",
        "refunds",
        type_="check",
    )

    op.drop_constraint(
        "ck_ledger_balance_after_nonnegative",
        "transaction_ledger",
        type_="check",
    )
    op.drop_constraint(
        "ck_ledger_balance_before_nonnegative",
        "transaction_ledger",
        type_="check",
    )
    op.drop_constraint(
        "ck_ledger_amount_positive",
        "transaction_ledger",
        type_="check",
    )

    op.drop_constraint(
        "ck_transaction_currency_uppercase",
        "transactions",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_status_valid",
        "transactions",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_type_valid",
        "transactions",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_amount_positive",
        "transactions",
        type_="check",
    )

    op.drop_constraint(
        "ck_transfer_currency_uppercase",
        "transfers",
        type_="check",
    )
    op.drop_constraint(
        "ck_transfer_status_valid",
        "transfers",
        type_="check",
    )
    op.drop_constraint(
        "ck_transfer_different_wallets",
        "transfers",
        type_="check",
    )
    op.drop_constraint(
        "ck_transfer_amount_positive",
        "transfers",
        type_="check",
    )

    op.drop_constraint(
        "ck_withdrawal_currency_uppercase",
        "withdrawals",
        type_="check",
    )
    op.drop_constraint(
        "ck_withdrawal_status_valid",
        "withdrawals",
        type_="check",
    )
    op.drop_constraint(
        "ck_withdrawal_amount_positive",
        "withdrawals",
        type_="check",
    )

    op.drop_constraint(
        "ck_deposit_currency_uppercase",
        "deposits",
        type_="check",
    )
    op.drop_constraint(
        "ck_deposit_status_valid",
        "deposits",
        type_="check",
    )
    op.drop_constraint(
        "ck_deposit_amount_positive",
        "deposits",
        type_="check",
    )

    op.drop_constraint(
        "ck_wallet_pending_balance_nonnegative",
        "wallet_balances",
        type_="check",
    )
    op.drop_constraint(
        "ck_wallet_available_balance_nonnegative",
        "wallet_balances",
        type_="check",
    )

    op.drop_constraint(
        "ck_wallet_currency_uppercase",
        "wallets",
        type_="check",
    )
    op.drop_constraint(
        "ck_wallet_status_valid",
        "wallets",
        type_="check",
    )

    op.drop_column("refresh_tokens", "created_at")
    op.drop_column("notifications", "created_at")
    op.drop_column("audit_logs", "created_at")