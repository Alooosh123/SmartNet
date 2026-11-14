"""Initial SmartNet schema baseline.

Revision ID: 0001_initial
Revises:

Keep this table list frozen. Do not use Base.metadata.create_all() without an
explicit table list here: future models would be created before their own
versioned migrations and later revisions would fail with "table already exists".
"""
from alembic import op
from database.database import Base
from database import models  # noqa: F401 - register all historical models

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# Tables present in the original application baseline only. Features introduced
# later belong to their own numbered revisions (0004 ops, 0005 wallet monitoring).
BASELINE_TABLE_NAMES = (
    "admins",
    "card_batches",
    "cards",
    "registration_requests",
    "clients",
    "chat_messages",
    "audit_logs",
    "system_settings",
)


def _baseline_tables():
    return [Base.metadata.tables[name] for name in BASELINE_TABLE_NAMES]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=_baseline_tables())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_baseline_tables())
