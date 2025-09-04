"""Fix timezone handling in datetime columns

Revision ID: efa8b52a6d32
Revises: dfbe7de3e5a3
Create Date: 2025-09-04 15:13:41.161872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "efa8b52a6d32"
down_revision: Union[str, None] = "dfbe7de3e5a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update datetime columns to be timezone-aware
    op.alter_column('download_jobs', 'created_at',
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=False)
    
    op.alter_column('download_jobs', 'started_at',
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=True)
    
    op.alter_column('download_jobs', 'completed_at',
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=True)
    
    op.alter_column('download_jobs', 'upload_date',
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True),
                    existing_nullable=True)


def downgrade() -> None:
    # Revert datetime columns back to timezone-naive
    op.alter_column('download_jobs', 'upload_date',
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=True)
    
    op.alter_column('download_jobs', 'completed_at',
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=True)
    
    op.alter_column('download_jobs', 'started_at',
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=True)
    
    op.alter_column('download_jobs', 'created_at',
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(),
                    existing_nullable=False)
