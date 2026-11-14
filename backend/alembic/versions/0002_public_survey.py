"""public QR survey: session axis/token/duration, per-device duplicate guard

Revision ID: 0002
Revises: 0001
"""
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("axis", sa.String(length=190), nullable=True))
    op.add_column("sessions", sa.Column("survey_token", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("survey_duration_minutes", sa.Integer(), nullable=True))

    bind = op.get_bind()
    ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM sessions"))]
    for sid in ids:
        bind.execute(
            sa.text("UPDATE sessions SET survey_token = :t WHERE id = :i"),
            {"t": secrets.token_urlsafe(16), "i": sid},
        )
    op.alter_column("sessions", "survey_token", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint("uq_sessions_survey_token", "sessions", ["survey_token"])

    op.add_column("survey_responses", sa.Column("device_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_response_session_device", "survey_responses", ["session_id", "device_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_response_session_device", "survey_responses", type_="unique")
    op.drop_column("survey_responses", "device_hash")
    op.drop_constraint("uq_sessions_survey_token", "sessions", type_="unique")
    op.drop_column("sessions", "survey_duration_minutes")
    op.drop_column("sessions", "survey_token")
    op.drop_column("sessions", "axis")
