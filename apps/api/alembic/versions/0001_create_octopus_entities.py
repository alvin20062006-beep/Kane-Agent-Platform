"""create octopus_entities table

Revision ID: 0001_create_octopus_entities
Revises: 
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_octopus_entities"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS octopus_entities (
          entity_type TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          data JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (entity_type, entity_id)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS octopus_entities;")

