import asyncio

from models import (
    Achievement,
    AdminUser,
    BlockedChannel,
    ChannelReward,
    ChatBoxSettings,
    ChatMessage,
    SecurityLog,
    SystemLog,
    TTSUserSettings,
    User,
    UserSession,
    UserSettings,
    UserToken,
    WhitelistedChannel,
)
from core.datetime_utils import utcnow_naive
from models.points import PointsTransaction, RewardQueue
from models.worker import TTSJob, TTSJobAttempt, Worker, WorkerPairingToken
from services.user_cleanup_service import UserDeletionResult, user_cleanup_service


def _create_target_user(db):
    user = User(
        twitch_username="delete_me",
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_related_rows(db, user: User, admin_user: User) -> None:
    token = UserToken(
        user_id=user.id,
        platform="twitch",
        platform_user_id="twitch-123",
        access_token="token",
    )
    reward = ChannelReward(
        user_id=user.id,
        platform="twitch",
        channel_name="delete_me",
        title="Reward",
        cost=100,
    )
    db.add_all(
        [
            token,
            UserSettings(user_id=user.id),
            TTSUserSettings(user_id=user.id),
            ChatBoxSettings(user_id=user.id, widget_token="widget-delete-me"),
            ChatMessage(user_id=user.id, channel_name="delete_me", platform="twitch", message="hello"),
            SecurityLog(event_type="login", user_id=user.id),
            SystemLog(admin_id=admin_user.id, action_type="test", target_user_id=user.id),
            WhitelistedChannel(channel_name="delete_me", platform="twitch"),
            BlockedChannel(channel_name="delete_me"),
            Achievement(
                channel_name="delete_me",
                name="Achievement",
                description="Test",
                type="messages",
                requirement_value=1,
                reward_type="points",
            ),
            UserSession(user_id=user.id, session_id="session-delete-me"),
            AdminUser(platform="twitch", platform_user_id="twitch-123", username="delete_me"),
            reward,
        ]
    )
    db.commit()
    db.refresh(reward)

    worker = Worker(
        owner_user_id=user.id,
        worker_key="worker-delete-me",
        label="Delete Me Worker",
        auth_token_hash="worker-hash-delete-me",
        supports_f5=True,
        status="offline",
        is_active=True,
    )
    pairing_token = WorkerPairingToken(
        owner_user_id=user.id,
        token_hash="pairing-hash-delete-me",
        provider_hint="f5",
        expires_at=utcnow_naive(),
    )
    db.add_all([worker, pairing_token])
    db.commit()
    db.refresh(worker)

    tts_job = TTSJob(
        id="job-delete-me",
        owner_user_id=user.id,
        created_by_user_id=user.id,
        target_worker_id=worker.id,
        assigned_worker_id=worker.id,
        provider="f5",
        text="hello world",
        payload={},
    )
    db.add(tts_job)
    db.commit()

    db.add(
        TTSJobAttempt(
            job_id=tts_job.id,
            worker_id=worker.id,
            provider="f5",
            status="completed",
            attempt_number=1,
        )
    )
    db.commit()

    db.add_all(
        [
            PointsTransaction(
                user_id=user.id,
                viewer_id="viewer-1",
                viewer_name="viewer",
                platform="twitch",
                channel_name="delete_me",
                transaction_type="earn",
                amount=50,
                reward_id=reward.id,
            ),
            RewardQueue(
                user_id=user.id,
                reward_id=reward.id,
                viewer_id="viewer-1",
                viewer_name="viewer",
                platform="twitch",
                channel_name="delete_me",
                points_cost=50,
            ),
        ]
    )
    db.commit()


def test_preview_user_deletion_counts_related_rows(db, admin_user):
    target_user = _create_target_user(db)
    _seed_related_rows(db, target_user, admin_user)

    preview = user_cleanup_service.preview_user_deletion(target_user.id, db)

    assert preview.user_id == target_user.id
    assert preview.username == "delete_me"
    assert preview.counts["user_tokens"] == 1
    assert preview.counts["user_settings"] == 1
    assert preview.counts["tts_user_settings"] == 1
    assert preview.counts["chatbox_settings"] == 1
    assert preview.counts["chat_messages"] == 1
    assert preview.counts["channel_rewards"] == 1
    assert preview.counts["points_transactions"] == 1
    assert preview.counts["reward_queue"] == 1
    assert preview.counts["whitelisted_channels"] == 1
    assert preview.counts["blocked_channels"] == 1
    assert preview.counts["achievements"] == 1
    assert preview.counts["worker_pairing_tokens"] == 1
    assert preview.counts["workers"] == 1
    assert preview.counts["tts_jobs"] == 1
    assert preview.counts["tts_job_attempts"] == 1
    assert preview.counts["admin_users"] == 1
    assert preview.counts["users"] == 1
    assert preview.total_rows >= 13


def test_permanently_delete_user_removes_rows_and_keeps_unrelated(db, admin_user, monkeypatch):
    target_user = _create_target_user(db)
    _seed_related_rows(db, target_user, admin_user)

    unrelated_user = User(twitch_username="keep_me", role="user", is_active=True)
    db.add(unrelated_user)
    db.commit()

    async def _noop_disconnect(user):
        return None

    monkeypatch.setattr(user_cleanup_service, "_disconnect_all_bots", _noop_disconnect)

    result = asyncio.run(
        user_cleanup_service.permanently_delete_user(
            target_user.id,
            db,
            actor_user_id=admin_user.id,
        )
    )

    assert isinstance(result, UserDeletionResult)
    assert result.success is True
    assert db.query(User).filter(User.id == target_user.id).first() is None
    assert db.query(User).filter(User.id == unrelated_user.id).first() is not None
    assert db.query(UserToken).filter(UserToken.user_id == target_user.id).count() == 0
    assert db.query(UserSettings).filter(UserSettings.user_id == target_user.id).count() == 0
    assert db.query(TTSUserSettings).filter(TTSUserSettings.user_id == target_user.id).count() == 0
    assert db.query(ChatMessage).filter(ChatMessage.user_id == target_user.id).count() == 0
    assert db.query(ChannelReward).filter(ChannelReward.user_id == target_user.id).count() == 0
    assert db.query(PointsTransaction).filter(PointsTransaction.user_id == target_user.id).count() == 0
    assert db.query(RewardQueue).filter(RewardQueue.user_id == target_user.id).count() == 0
    assert db.query(WorkerPairingToken).filter(WorkerPairingToken.owner_user_id == target_user.id).count() == 0
    assert db.query(Worker).filter(Worker.owner_user_id == target_user.id).count() == 0
    assert db.query(TTSJob).filter(TTSJob.owner_user_id == target_user.id).count() == 0
    assert db.query(TTSJobAttempt).join(TTSJob, TTSJobAttempt.job_id == TTSJob.id).filter(TTSJob.owner_user_id == target_user.id).count() == 0


def test_admin_permanent_delete_endpoint_returns_deleted_counts(admin_client, db, admin_user, monkeypatch):
    target_user = _create_target_user(db)
    _seed_related_rows(db, target_user, admin_user)

    async def _noop_disconnect(user):
        return None

    monkeypatch.setattr(user_cleanup_service, "_disconnect_all_bots", _noop_disconnect)

    response = admin_client.post(f"/api/admin/permanently-delete-user/{target_user.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["deleted_data"]["users"] == 1
    assert db.query(User).filter(User.id == target_user.id).first() is None
