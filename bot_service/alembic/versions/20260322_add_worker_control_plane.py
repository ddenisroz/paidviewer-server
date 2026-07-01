"""Add worker control-plane tables.

Revision ID: 20260322_worker_control
Revises: 20260316_fix_speed_preset
Create Date: 2026-03-22 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260322_worker_control"
down_revision: Union[str, Sequence[str], None] = "20260316_fix_speed_preset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("worker_key", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("label", sa.String(), nullable=False, server_default="TTS Worker"),
        sa.Column("auth_token_hash", sa.String(), nullable=False),
        sa.Column("supports_f5", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supports_qwen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("runtime_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(), nullable=False, server_default="offline"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("worker_key"),
        sa.UniqueConstraint("auth_token_hash"),
    )
    op.create_index("ix_workers_id", "workers", ["id"])
    op.create_index("ix_workers_worker_key", "workers", ["worker_key"])
    op.create_index("ix_workers_owner_user_id", "workers", ["owner_user_id"])
    op.create_index("ix_workers_status", "workers", ["status"])
    op.create_index("ix_workers_last_seen_at", "workers", ["last_seen_at"])
    op.create_index("ix_workers_is_active", "workers", ["is_active"])
    op.create_index("ix_workers_is_managed", "workers", ["is_managed"])
    op.create_index("ix_workers_supports_f5", "workers", ["supports_f5"])
    op.create_index("ix_workers_supports_qwen", "workers", ["supports_qwen"])
    op.create_index("ix_workers_owner_active", "workers", ["owner_user_id", "is_active"])
    op.create_index("ix_workers_status_active", "workers", ["status", "is_active"])

    op.create_table(
        "worker_pairing_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("label_hint", sa.String(), nullable=True),
        sa.Column("provider_hint", sa.String(), nullable=True),
        sa.Column("is_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_worker_pairing_tokens_id", "worker_pairing_tokens", ["id"])
    op.create_index("ix_worker_pairing_tokens_owner_user_id", "worker_pairing_tokens", ["owner_user_id"])
    op.create_index("ix_worker_pairing_tokens_token_hash", "worker_pairing_tokens", ["token_hash"])
    op.create_index("ix_worker_pairing_tokens_is_managed", "worker_pairing_tokens", ["is_managed"])
    op.create_index("ix_worker_pairing_tokens_expires_at", "worker_pairing_tokens", ["expires_at"])
    op.create_index("ix_worker_pairing_tokens_used_at", "worker_pairing_tokens", ["used_at"])
    op.create_index(
        "ix_worker_pairing_tokens_owner_expires",
        "worker_pairing_tokens",
        ["owner_user_id", "expires_at"],
    )

    op.create_table(
        "tts_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("target_worker_id", sa.Integer(), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("assigned_worker_id", sa.Integer(), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("voice", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("result_audio_url", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tts_jobs_id", "tts_jobs", ["id"])
    op.create_index("ix_tts_jobs_owner_user_id", "tts_jobs", ["owner_user_id"])
    op.create_index("ix_tts_jobs_created_by_user_id", "tts_jobs", ["created_by_user_id"])
    op.create_index("ix_tts_jobs_target_worker_id", "tts_jobs", ["target_worker_id"])
    op.create_index("ix_tts_jobs_assigned_worker_id", "tts_jobs", ["assigned_worker_id"])
    op.create_index("ix_tts_jobs_provider", "tts_jobs", ["provider"])
    op.create_index("ix_tts_jobs_status", "tts_jobs", ["status"])
    op.create_index("ix_tts_jobs_scheduled_at", "tts_jobs", ["scheduled_at"])
    op.create_index("ix_tts_jobs_lease_expires_at", "tts_jobs", ["lease_expires_at"])
    op.create_index("ix_tts_jobs_status_schedule", "tts_jobs", ["status", "scheduled_at"])
    op.create_index("ix_tts_jobs_owner_status", "tts_jobs", ["owner_user_id", "status"])
    op.create_index("ix_tts_jobs_target_worker_status", "tts_jobs", ["target_worker_id", "status"])

    op.create_table(
        "tts_job_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("tts_jobs.id"), nullable=False),
        sa.Column("worker_id", sa.Integer(), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="leased"),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("result_audio_url", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_tts_job_attempts_id", "tts_job_attempts", ["id"])
    op.create_index("ix_tts_job_attempts_job_id", "tts_job_attempts", ["job_id"])
    op.create_index("ix_tts_job_attempts_worker_id", "tts_job_attempts", ["worker_id"])
    op.create_index("ix_tts_job_attempts_provider", "tts_job_attempts", ["provider"])
    op.create_index("ix_tts_job_attempts_status", "tts_job_attempts", ["status"])
    op.create_index("ix_tts_job_attempts_job_attempt", "tts_job_attempts", ["job_id", "attempt_number"])


def downgrade() -> None:
    op.drop_index("ix_tts_job_attempts_job_attempt", table_name="tts_job_attempts")
    op.drop_index("ix_tts_job_attempts_status", table_name="tts_job_attempts")
    op.drop_index("ix_tts_job_attempts_provider", table_name="tts_job_attempts")
    op.drop_index("ix_tts_job_attempts_worker_id", table_name="tts_job_attempts")
    op.drop_index("ix_tts_job_attempts_job_id", table_name="tts_job_attempts")
    op.drop_index("ix_tts_job_attempts_id", table_name="tts_job_attempts")
    op.drop_table("tts_job_attempts")

    op.drop_index("ix_tts_jobs_target_worker_status", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_owner_status", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_status_schedule", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_lease_expires_at", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_scheduled_at", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_status", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_provider", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_assigned_worker_id", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_target_worker_id", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_created_by_user_id", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_owner_user_id", table_name="tts_jobs")
    op.drop_index("ix_tts_jobs_id", table_name="tts_jobs")
    op.drop_table("tts_jobs")

    op.drop_index("ix_worker_pairing_tokens_owner_expires", table_name="worker_pairing_tokens")
    op.drop_index("ix_worker_pairing_tokens_used_at", table_name="worker_pairing_tokens")
    op.drop_index("ix_worker_pairing_tokens_expires_at", table_name="worker_pairing_tokens")
    op.drop_index("ix_worker_pairing_tokens_is_managed", table_name="worker_pairing_tokens")
    op.drop_index("ix_worker_pairing_tokens_token_hash", table_name="worker_pairing_tokens")
    op.drop_index("ix_worker_pairing_tokens_owner_user_id", table_name="worker_pairing_tokens")
    op.drop_index("ix_worker_pairing_tokens_id", table_name="worker_pairing_tokens")
    op.drop_table("worker_pairing_tokens")

    op.drop_index("ix_workers_status_active", table_name="workers")
    op.drop_index("ix_workers_owner_active", table_name="workers")
    op.drop_index("ix_workers_supports_qwen", table_name="workers")
    op.drop_index("ix_workers_supports_f5", table_name="workers")
    op.drop_index("ix_workers_is_managed", table_name="workers")
    op.drop_index("ix_workers_is_active", table_name="workers")
    op.drop_index("ix_workers_last_seen_at", table_name="workers")
    op.drop_index("ix_workers_status", table_name="workers")
    op.drop_index("ix_workers_owner_user_id", table_name="workers")
    op.drop_index("ix_workers_worker_key", table_name="workers")
    op.drop_index("ix_workers_id", table_name="workers")
    op.drop_table("workers")
