"""trainee national id, phone length, and organization

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trainees", sa.Column("organization", sa.String(length=160), nullable=True))
    op.add_column("trainees", sa.Column("national_id", sa.String(length=14), nullable=True))
    op.create_unique_constraint("uq_trainees_national_id", "trainees", ["national_id"])
    op.alter_column("trainees", "phone", existing_type=sa.String(length=32), type_=sa.String(length=11), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("trainees", "phone", existing_type=sa.String(length=11), type_=sa.String(length=32), existing_nullable=True)
    op.drop_constraint("uq_trainees_national_id", "trainees", type_="unique")
    op.drop_column("trainees", "national_id")
    op.drop_column("trainees", "organization")
