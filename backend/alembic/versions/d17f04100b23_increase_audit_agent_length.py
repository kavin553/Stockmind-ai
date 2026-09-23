from alembic import op
import sqlalchemy as sa

revision = "d17f04100b23"
down_revision = "cfb103bf54c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "agent",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "agent",
        existing_type=sa.String(length=128),
        type_=sa.String(length=32),
        existing_nullable=True,
    )