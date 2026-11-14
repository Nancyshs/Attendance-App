"""trainee governorate and job title

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trainees", sa.Column("governorate", sa.String(length=80), nullable=True))
    op.add_column("trainees", sa.Column("job_title", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("trainees", "job_title")
    op.drop_column("trainees", "governorate")
