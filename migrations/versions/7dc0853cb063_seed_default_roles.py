

from alembic import op
import sqlalchemy as sa


revision = "7dc0853cb063"
down_revision = "abda02a0b6b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles_table = sa.table(
        "roles",
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )

    op.bulk_insert(
        roles_table,
        [
            {
                "name": "Super Admin",
                "description": "Full system access",
            },
            {
                "name": "Admin",
                "description": "Administrative access",
            },
            {
                "name": "Support Agent",
                "description": "Customer support operations",
            },
            {
                "name": "Customer",
                "description": "Standard customer access",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM roles
            WHERE name IN (
                'Super Admin',
                'Admin',
                'Support Agent',
                'Customer'
            )
            """
        )
    )
