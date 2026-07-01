"""Fix user voice speed_preset type back to string presets.

Revision ID: 20260316_fix_speed_preset
Revises: 20260222_add_tts_provider_split
Create Date: 2026-03-16 12:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260316_fix_speed_preset"
down_revision: Union[str, Sequence[str], None] = "20260222_add_tts_provider_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            """
            ALTER TABLE user_voice_settings
            ALTER COLUMN speed_preset TYPE VARCHAR
            USING CASE
                WHEN speed_preset IS NULL THEN NULL
                WHEN speed_preset = 0 THEN 'very_slow'
                WHEN speed_preset = 1 THEN 'slow'
                WHEN speed_preset = 2 THEN 'normal'
                WHEN speed_preset = 3 THEN 'fast'
                WHEN speed_preset = 4 THEN 'very_fast'
                ELSE trim(to_char(speed_preset, 'FM999999999.################'))
            END
            """
        )
        return

    with op.batch_alter_table("user_voice_settings") as batch_op:
        batch_op.alter_column(
            "speed_preset",
            existing_type=sa.Float(),
            type_=sa.String(),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            """
            ALTER TABLE user_voice_settings
            ALTER COLUMN speed_preset TYPE FLOAT
            USING CASE
                WHEN speed_preset IS NULL THEN NULL
                WHEN speed_preset = 'very_slow' THEN 0
                WHEN speed_preset = 'slow' THEN 1
                WHEN speed_preset = 'normal' THEN 2
                WHEN speed_preset = 'fast' THEN 3
                WHEN speed_preset = 'very_fast' THEN 4
                WHEN speed_preset ~ '^[0-9]*\\.?[0-9]+$' THEN speed_preset::double precision
                ELSE NULL
            END
            """
        )
        return

    with op.batch_alter_table("user_voice_settings") as batch_op:
        batch_op.alter_column(
            "speed_preset",
            existing_type=sa.String(),
            type_=sa.Float(),
            existing_nullable=True,
        )
