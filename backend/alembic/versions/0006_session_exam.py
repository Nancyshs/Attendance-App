"""true/false exam on each session, sat before and after the lecture

Revision ID: 0006
Revises: 0005
"""
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("exam_token", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("exam_before_start", sa.Time(), nullable=True))
    op.add_column("sessions", sa.Column("exam_before_end", sa.Time(), nullable=True))
    op.add_column("sessions", sa.Column("exam_after_start", sa.Time(), nullable=True))
    op.add_column("sessions", sa.Column("exam_after_end", sa.Time(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM sessions")).fetchall()
    for (sid,) in rows:
        conn.execute(
            sa.text("UPDATE sessions SET exam_token = :token WHERE id = :id"),
            {"token": secrets.token_urlsafe(16), "id": sid},
        )
    op.alter_column("sessions", "exam_token", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint("uq_sessions_exam_token", "sessions", ["exam_token"])

    op.create_table(
        "exam_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_exam_questions_session", "exam_questions", ["session_id"])
    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trainee_id", sa.Integer(), sa.ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(length=8), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "trainee_id", "phase", name="uq_exam_attempt"),
    )
    op.create_table(
        "exam_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("exam_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("exam_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exam_answers")
    op.drop_table("exam_attempts")
    op.drop_index("ix_exam_questions_session", table_name="exam_questions")
    op.drop_table("exam_questions")
    op.drop_constraint("uq_sessions_exam_token", "sessions", type_="unique")
    op.drop_column("sessions", "exam_after_end")
    op.drop_column("sessions", "exam_after_start")
    op.drop_column("sessions", "exam_before_end")
    op.drop_column("sessions", "exam_before_start")
    op.drop_column("sessions", "exam_token")
