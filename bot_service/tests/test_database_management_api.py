from datetime import timedelta

from core.datetime_utils import utcnow_naive
from models import User, UserSession, UserSettings
from models.drops import DropsConfig, DropsHistory, DropsQuality, DropsReward, MythicalDropsSession, StreamSession, UserStreak
from models.youtube import YouTubeQueue


def test_database_hygiene_preview_endpoint(admin_client, db):
    admin = db.query(User).filter(User.role == "admin").first()
    assert admin is not None
    db.add(DropsQuality(id=998, name="PreviewQuality", color="#ffffff", weight=1))
    db.commit()

    db.add_all(
        [
            UserSettings(user_id=999),
            UserSettings(session_id="legacy-preview-settings"),
            YouTubeQueue(
                session_id="legacy-preview-queue",
                video_url="https://youtube.com/watch?v=preview",
                video_id="previewqueue",
                title="Preview Queue",
                channel_name="preview_owner",
                platform="twitch",
                requester_name="preview",
                requester_id="preview",
                position=1,
                status="pending",
            ),
            DropsConfig(session_id="legacy-preview-drops-config", channel_name="preview_owner", platform="global"),
            DropsReward(
                session_id="legacy-preview-drops-reward",
                channel_name="preview_owner",
                platform="twitch",
                name="Preview Reward",
                quality_id=998,
                weight=1,
                reward_type="points",
                reward_value="1",
                is_active=True,
            ),
            UserStreak(
                session_id="legacy-preview-streak",
                channel_name="preview_owner",
                platform="twitch",
                viewer_id="viewer1",
                viewer_name="viewer1",
            ),
            DropsHistory(
                session_id="legacy-preview-history",
                channel_name="preview_owner",
                platform="twitch",
                viewer_id="viewer1",
                viewer_name="viewer1",
                lootbox_type="streak",
                quality_id=998,
                reward_name="Preview Reward",
                reward_type="points",
                reward_value="1",
            ),
            MythicalDropsSession(
                session_id="legacy-preview-mythical",
                channel_name="preview_owner",
                platform="twitch",
                donation_amount=1000.0,
                window_duration_minutes=5,
                expires_at=utcnow_naive(),
            ),
            StreamSession(
                session_id="legacy-preview-stream",
                channel_name="preview_owner",
                platform="twitch",
                started_at=utcnow_naive(),
                is_active=False,
            ),
            UserSession(
                user_id=admin.id,
                session_id="inactive-preview-session",
                device_info={"platform": "twitch"},
                is_active=False,
                created_at=utcnow_naive() - timedelta(days=10),
                last_activity=utcnow_naive() - timedelta(days=10),
            ),
        ]
    )
    db.commit()

    response = admin_client.get("/api/database/hygiene/preview?inactive_session_days=7")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["orphan_user_records"]["tables"]["user_settings"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["user_settings"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["youtube_queue"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["drops_configs"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["drops_rewards"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["user_streaks"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["drops_history"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["mythical_drops_sessions"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["stream_sessions"] == 1
    assert payload["data"]["inactive_sessions"]["old_inactive_sessions"] == 1


def test_database_hygiene_cleanup_endpoint(admin_client, db):
    admin = db.query(User).filter(User.role == "admin").first()
    assert admin is not None
    db.add(DropsQuality(id=997, name="CleanupQuality", color="#ffffff", weight=1))
    db.commit()

    db.add_all(
        [
            UserSettings(user_id=999),
            UserSettings(session_id="legacy-cleanup-settings"),
            YouTubeQueue(
                session_id="legacy-cleanup-queue",
                video_url="https://youtube.com/watch?v=cleanup",
                video_id="cleanupqueue",
                title="Cleanup Queue",
                channel_name="cleanup_owner",
                platform="twitch",
                requester_name="cleanup",
                requester_id="cleanup",
                position=1,
                status="pending",
            ),
            DropsConfig(session_id="legacy-cleanup-drops-config", channel_name="cleanup_owner", platform="global"),
            DropsReward(
                session_id="legacy-cleanup-drops-reward",
                channel_name="cleanup_owner",
                platform="twitch",
                name="Cleanup Reward",
                quality_id=997,
                weight=1,
                reward_type="points",
                reward_value="1",
                is_active=True,
            ),
            UserStreak(
                session_id="legacy-cleanup-streak",
                channel_name="cleanup_owner",
                platform="twitch",
                viewer_id="viewer1",
                viewer_name="viewer1",
            ),
            DropsHistory(
                session_id="legacy-cleanup-history",
                channel_name="cleanup_owner",
                platform="twitch",
                viewer_id="viewer1",
                viewer_name="viewer1",
                lootbox_type="streak",
                quality_id=997,
                reward_name="Cleanup Reward",
                reward_type="points",
                reward_value="1",
            ),
            MythicalDropsSession(
                session_id="legacy-cleanup-mythical",
                channel_name="cleanup_owner",
                platform="twitch",
                donation_amount=1000.0,
                window_duration_minutes=5,
                expires_at=utcnow_naive(),
            ),
            StreamSession(
                session_id="legacy-cleanup-stream",
                channel_name="cleanup_owner",
                platform="twitch",
                started_at=utcnow_naive(),
                is_active=False,
            ),
            UserSession(
                user_id=admin.id,
                session_id="inactive-cleanup-session",
                device_info={"platform": "twitch"},
                is_active=False,
                created_at=utcnow_naive() - timedelta(days=10),
                last_activity=utcnow_naive() - timedelta(days=10),
            ),
        ]
    )
    db.commit()

    response = admin_client.post(
        "/api/database/hygiene/cleanup",
        json={
            "clean_orphan_users": True,
            "clean_legacy_session_records": True,
            "clean_inactive_sessions": True,
            "inactive_session_days": 7,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["orphan_user_records"]["tables"]["user_settings"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["user_settings"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["youtube_queue"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["drops_configs"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["drops_rewards"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["user_streaks"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["drops_history"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["mythical_drops_sessions"] == 1
    assert payload["data"]["legacy_session_records"]["tables"]["stream_sessions"] == 1
    assert payload["data"]["inactive_sessions"]["deleted_sessions"] == 1
    assert db.query(UserSettings).filter(UserSettings.user_id == 999).count() == 0
    assert db.query(UserSettings).filter(UserSettings.session_id == "legacy-cleanup-settings").count() == 0
    assert db.query(YouTubeQueue).filter(YouTubeQueue.session_id == "legacy-cleanup-queue").count() == 0
    assert db.query(DropsConfig).filter(DropsConfig.session_id == "legacy-cleanup-drops-config").count() == 0
    assert db.query(DropsReward).filter(DropsReward.session_id == "legacy-cleanup-drops-reward").count() == 0
    assert db.query(UserStreak).filter(UserStreak.session_id == "legacy-cleanup-streak").count() == 0
    assert db.query(DropsHistory).filter(DropsHistory.session_id == "legacy-cleanup-history").count() == 0
    assert db.query(MythicalDropsSession).filter(MythicalDropsSession.session_id == "legacy-cleanup-mythical").count() == 0
    assert db.query(StreamSession).filter(StreamSession.session_id == "legacy-cleanup-stream").count() == 0
    assert db.query(UserSession).filter(UserSession.session_id == "inactive-cleanup-session").count() == 0
