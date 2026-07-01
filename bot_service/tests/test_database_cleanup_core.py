from core.datetime_utils import utcnow_naive
from models import User, UserSession, UserSettings
from models.drops import DropsConfig, DropsHistory, DropsQuality, DropsReward, MythicalDropsSession, StreamSession, UserStreak
from models.youtube import YouTubeQueue
from models.tts import TTSUserSettings
from services.database_maintenance.database_cleanup_core import DatabaseCleanupCore


def test_preview_orphan_user_records_counts_only_missing_user_rows(db):
    user = User(twitch_username="cleanup_owner", role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add_all(
        [
            UserSettings(user_id=user.id),
            UserSettings(user_id=999),
            UserSettings(session_id="legacy-session-settings"),
            TTSUserSettings(user_id=user.id),
            TTSUserSettings(user_id=999),
            TTSUserSettings(session_id="legacy-session-tts"),
        ]
    )
    db.commit()

    cleanup_core = DatabaseCleanupCore(db)
    preview = cleanup_core.preview_orphan_user_records()

    assert preview["tables"]["user_settings"] == 1
    assert preview["tables"]["tts_user_settings"] == 1
    assert preview["total_rows"] == 2


def test_cleanup_orphan_user_records_removes_only_orphans(db):
    user = User(twitch_username="cleanup_owner", role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add_all(
        [
            UserSettings(user_id=user.id),
            UserSettings(user_id=999),
            UserSettings(session_id="legacy-session-settings"),
            TTSUserSettings(user_id=user.id),
            TTSUserSettings(user_id=999),
            TTSUserSettings(session_id="legacy-session-tts"),
        ]
    )
    db.commit()

    cleanup_core = DatabaseCleanupCore(db)
    result = cleanup_core.cleanup_orphan_user_records()

    assert result["tables"]["user_settings"] == 1
    assert result["tables"]["tts_user_settings"] == 1
    assert result["total_rows"] == 2
    assert db.query(UserSettings).filter(UserSettings.user_id == user.id).count() == 1
    assert db.query(UserSettings).filter(UserSettings.session_id == "legacy-session-settings").count() == 1
    assert db.query(UserSettings).filter(UserSettings.user_id == 999).count() == 0
    assert db.query(TTSUserSettings).filter(TTSUserSettings.user_id == user.id).count() == 1
    assert db.query(TTSUserSettings).filter(TTSUserSettings.session_id == "legacy-session-tts").count() == 1
    assert db.query(TTSUserSettings).filter(TTSUserSettings.user_id == 999).count() == 0


def test_cleanup_legacy_session_records_removes_only_session_scoped_rows(db):
    user = User(twitch_username="legacy_cleanup_owner", role="user", is_active=True)
    db.add(user)
    db.add(DropsQuality(id=999, name="LegacyQuality", color="#ffffff", weight=1))
    db.commit()
    db.refresh(user)

    db.add_all(
        [
            UserSettings(user_id=user.id),
            UserSettings(session_id="legacy-session-settings"),
            TTSUserSettings(user_id=user.id),
            TTSUserSettings(session_id="legacy-session-tts"),
            YouTubeQueue(
                session_id="legacy-session-queue",
                video_url="https://youtube.com/watch?v=legacy",
                video_id="legacyqueue1",
                title="Legacy Queue",
                channel_name="legacy_owner",
                platform="twitch",
                requester_name="legacy",
                requester_id="legacy",
                position=1,
                status="pending",
            ),
            DropsConfig(session_id="legacy-session-drops-config", channel_name="legacy_owner", platform="global"),
            DropsReward(
                session_id="legacy-session-drops-reward",
                channel_name="legacy_owner",
                platform="twitch",
                name="Legacy Reward",
                quality_id=999,
                weight=1,
                reward_type="points",
                reward_value="1",
                is_active=True,
            ),
            UserStreak(
                session_id="legacy-session-streak",
                channel_name="legacy_owner",
                platform="twitch",
                viewer_id="viewer1",
                viewer_name="viewer1",
            ),
            DropsHistory(
                session_id="legacy-session-history",
                channel_name="legacy_owner",
                platform="twitch",
                viewer_id="viewer1",
                viewer_name="viewer1",
                lootbox_type="streak",
                quality_id=999,
                reward_name="Legacy Reward",
                reward_type="points",
                reward_value="1",
            ),
            MythicalDropsSession(
                session_id="legacy-session-mythical",
                channel_name="legacy_owner",
                platform="twitch",
                donation_amount=1000.0,
                window_duration_minutes=5,
                expires_at=utcnow_naive(),
            ),
            StreamSession(
                session_id="legacy-session-stream",
                channel_name="legacy_owner",
                platform="twitch",
                started_at=utcnow_naive(),
                is_active=False,
            ),
        ]
    )
    db.commit()

    cleanup_core = DatabaseCleanupCore(db)
    preview = cleanup_core.preview_legacy_session_records()
    result = cleanup_core.cleanup_legacy_session_records()

    assert preview["tables"]["user_settings"] == 1
    assert preview["tables"]["tts_user_settings"] == 1
    assert preview["tables"]["youtube_queue"] == 1
    assert preview["tables"]["drops_configs"] == 1
    assert preview["tables"]["drops_rewards"] == 1
    assert preview["tables"]["user_streaks"] == 1
    assert preview["tables"]["drops_history"] == 1
    assert preview["tables"]["mythical_drops_sessions"] == 1
    assert preview["tables"]["stream_sessions"] == 1
    assert preview["total_rows"] == 9
    assert result["tables"]["user_settings"] == 1
    assert result["tables"]["tts_user_settings"] == 1
    assert result["tables"]["youtube_queue"] == 1
    assert result["tables"]["drops_configs"] == 1
    assert result["tables"]["drops_rewards"] == 1
    assert result["tables"]["user_streaks"] == 1
    assert result["tables"]["drops_history"] == 1
    assert result["tables"]["mythical_drops_sessions"] == 1
    assert result["tables"]["stream_sessions"] == 1
    assert result["total_rows"] == 9
    assert db.query(UserSettings).filter(UserSettings.user_id == user.id).count() == 1
    assert db.query(UserSettings).filter(UserSettings.session_id == "legacy-session-settings").count() == 0
    assert db.query(TTSUserSettings).filter(TTSUserSettings.user_id == user.id).count() == 1
    assert db.query(TTSUserSettings).filter(TTSUserSettings.session_id == "legacy-session-tts").count() == 0
    assert db.query(YouTubeQueue).filter(YouTubeQueue.session_id == "legacy-session-queue").count() == 0
    assert db.query(DropsConfig).filter(DropsConfig.session_id == "legacy-session-drops-config").count() == 0
    assert db.query(DropsReward).filter(DropsReward.session_id == "legacy-session-drops-reward").count() == 0
    assert db.query(UserStreak).filter(UserStreak.session_id == "legacy-session-streak").count() == 0
    assert db.query(DropsHistory).filter(DropsHistory.session_id == "legacy-session-history").count() == 0
    assert db.query(MythicalDropsSession).filter(MythicalDropsSession.session_id == "legacy-session-mythical").count() == 0
    assert db.query(StreamSession).filter(StreamSession.session_id == "legacy-session-stream").count() == 0


def test_cleanup_inactive_sessions_respects_activity_and_retention(db):
    from datetime import timedelta

    user = User(twitch_username="session_owner", role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    now = utcnow_naive()

    db.add_all(
        [
            UserSession(
                user_id=user.id,
                session_id="active-old-session",
                device_info={"platform": "twitch"},
                is_active=True,
                created_at=now - timedelta(days=14),
                last_activity=now - timedelta(days=14),
            ),
            UserSession(
                user_id=user.id,
                session_id="inactive-recent-session",
                device_info={"platform": "twitch"},
                is_active=False,
                created_at=now - timedelta(days=2),
                last_activity=now - timedelta(days=2),
            ),
            UserSession(
                user_id=user.id,
                session_id="inactive-old-session",
                device_info={"platform": "twitch"},
                is_active=False,
                created_at=now - timedelta(days=14),
                last_activity=now - timedelta(days=14),
            ),
        ]
    )
    db.commit()

    cleanup_core = DatabaseCleanupCore(db)
    preview = cleanup_core.preview_inactive_session_cleanup(days_old=7)
    result = cleanup_core.cleanup_inactive_sessions(days_old=7)

    assert preview["old_inactive_sessions"] == 1
    assert result["deleted_sessions"] == 1
    assert db.query(UserSession).filter(UserSession.session_id == "inactive-old-session").count() == 0
    assert db.query(UserSession).filter(UserSession.session_id == "inactive-recent-session").count() == 1
    assert db.query(UserSession).filter(UserSession.session_id == "active-old-session").count() == 1
