"""
Comprehensive test suite for Drops system functionality
Tests drops opening mechanism, streak tracking, donation-triggered drops, and reward calculation
"""

import pytest
import sys
from pathlib import Path

# Add bot_service to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

from core.database import (
    Base,
    DropsConfig,
    DropsReward,
    DropsQuality,
    UserStreak,
    DropsHistory,
    MythicalDropsSession,
    PendingStreakChest,
)
from services.drops.drops_service import DropsService
from services.drops.drops_calculation_service import DropsCalculationService
from services.stream_session_service import StreamSessionService
from repositories.drops_history_repository import DropsHistoryRepository
from core.datetime_utils import utcnow_naive


@pytest.fixture
def db_session():
    """Create a test database session"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create default qualities
    qualities = [
        DropsQuality(id=1, name="Common", color="#808080", weight=100),
        DropsQuality(id=2, name="Rare", color="#0070dd", weight=100),
        DropsQuality(id=3, name="Epic", color="#a335ee", weight=100),
        DropsQuality(id=4, name="Legendary", color="#ff8000", weight=100),
        DropsQuality(id=5, name="Mythical", color="#e6cc80", weight=100),
    ]
    for quality in qualities:
        session.add(quality)
    session.commit()

    yield session
    session.close()


@pytest.fixture
def drops_service(db_session):
    """Create a DropsService instance"""
    return DropsService(db_session)


@pytest.fixture
def drops_calc_service(db_session):
    """Create a DropsCalculationService instance"""
    return DropsCalculationService(db_session)


@pytest.fixture
def test_config(db_session):
    """Create a test drops configuration"""
    config = DropsConfig(
        user_id=1,
        channel_name="test_channel",
        platform="global",
        # Streak settings
        streak_days_common=1,
        streak_days_rare=3,
        streak_days_epic=7,
        streak_days_legendary=14,
        streak_messages_required=5,
        streak_reset_on_skip=True,
        streak_enabled_twitch=True,
        streak_enabled_vk=True,
        # Donation settings
        donation_enabled=True,
        donation_amount_common=50.0,
        donation_amount_rare=100.0,
        donation_amount_epic=500.0,
        donation_amount_legendary=1000.0,
        # Mythical settings
        mythical_enabled=True,
        mythical_min_interval_hours=2,
        mythical_max_interval_hours=8,
        mythical_window_duration_minutes=5,
        mythical_donation_amount=2000.0,
        # Widget settings
        widget_spinning_duration_ms=1500,
        widget_opening_duration_ms=1000,
        widget_result_duration_ms=5500,
        widget_closing_duration_ms=500,
    )
    db_session.add(config)
    db_session.commit()
    return config


@pytest.fixture
def test_rewards(db_session):
    """Create test rewards for each quality"""
    rewards = []
    qualities = db_session.query(DropsQuality).all()

    for quality in qualities:
        for i in range(3):  # 3 rewards per quality
            reward = DropsReward(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",  # Platform is stored but rewards are cross-platform
                name=f"{quality.name} Reward {i + 1}",
                description=f"Test {quality.name} reward",
                quality_id=quality.id,
                weight=100 if i == 0 else (50 if i == 1 else 25),  # Different weights
                reward_type="points",
                reward_value="100",
                is_active=True,
            )
            db_session.add(reward)
            rewards.append(reward)

    db_session.commit()
    return rewards


class TestDropsOpening:
    """Test drops opening mechanism"""

    def test_calculate_drop_basic(self, drops_calc_service, test_config, test_rewards):
        """Test basic drop calculation"""
        result = drops_calc_service.calculate_drop(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            quality_name="Common",
        )

        assert result is not None
        assert "reward_id" in result
        assert "reward_name" in result
        assert "quality" in result
        assert result["quality"] == "Common"
        print(f"[OK] Basic drop calculation works: {result['reward_name']}")

    def test_calculate_drop_all_qualities(
        self, drops_calc_service, test_config, test_rewards
    ):
        """Test drop calculation for all quality tiers"""
        qualities = ["Common", "Rare", "Epic", "Legendary", "Mythical"]

        for quality in qualities:
            result = drops_calc_service.calculate_drop(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                quality_name=quality,
            )

            assert result is not None
            assert result["quality"] == quality
            print(f"[OK] {quality} drop calculation works")

    def test_weighted_random_selection(
        self, drops_calc_service, test_config, test_rewards
    ):
        """Test that weighted random selection respects weights"""
        # Run multiple calculations and check distribution
        results = {}
        iterations = 1000

        for _ in range(iterations):
            result = drops_calc_service.calculate_drop(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                quality_name="Common",
            )
            reward_name = result["reward_name"]
            results[reward_name] = results.get(reward_name, 0) + 1

        # Check that higher weight rewards appear more often
        # Weights are 100, 50, 25 (total 175)
        # Expected probabilities: ~57%, ~29%, ~14%
        print(f"[OK] Weighted selection distribution over {iterations} iterations:")
        for reward_name, count in sorted(
            results.items(), key=lambda x: x[1], reverse=True
        ):
            percentage = (count / iterations) * 100
            print(f"   {reward_name}: {count} times ({percentage:.1f}%)")

        # Basic sanity check: highest weight should appear most often
        most_common = max(results.items(), key=lambda x: x[1])[0]
        assert "Reward 1" in most_common  # Reward 1 has weight 100

    def test_drop_invalid_quality(self, drops_calc_service, test_config, test_rewards):
        """Test drop calculation with invalid quality"""
        with pytest.raises(ValueError, match="Quality .* not found"):
            drops_calc_service.calculate_drop(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                quality_name="InvalidQuality",
            )
        print("[OK] Invalid quality handling works")

    def test_drop_no_rewards(self, drops_calc_service, test_config, db_session):
        """Test drop calculation when no rewards exist"""
        # Create a new quality without rewards
        new_quality = DropsQuality(
            id=10, name="TestQuality", color="#000000", weight=100
        )
        db_session.add(new_quality)
        db_session.commit()

        with pytest.raises(ValueError, match="No rewards available"):
            drops_calc_service.calculate_drop(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                quality_name="TestQuality",
            )
        print("[OK] No rewards handling works")


class TestStreakTracking:
    """Test streak tracking functionality"""

    def test_create_new_streak(self, drops_service, test_config):
        """Test creating a new streak"""
        streak = drops_service.get_user_streak(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
        )

        assert streak is None  # No streak exists yet

        # Increment message count (creates streak)
        streak = drops_service.increment_viewer_message_count(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
        )

        assert streak is not None
        assert streak.viewer_id == "viewer123"
        assert streak.messages_this_stream == 1
        assert streak.current_streak == 0  # No streak yet
        print("[OK] New streak creation works")

    def test_increment_message_count(self, drops_service, test_config):
        """Test incrementing message count"""
        # Create initial streak
        streak = drops_service.increment_viewer_message_count(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
        )
        initial_count = streak.messages_this_stream

        # Increment again
        streak = drops_service.increment_viewer_message_count(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
        )

        assert streak.messages_this_stream == initial_count + 1
        print(
            f"[OK] Message count increment works: {initial_count} -> {streak.messages_this_stream}"
        )

    def test_streak_quality_determination(self, drops_service, test_config):
        """Test streak quality determination based on days"""
        # Test different streak days
        test_cases = [
            (1, "Common"),
            (3, "Rare"),
            (7, "Epic"),
            (14, "Legendary"),
        ]

        for days, expected_quality in test_cases:
            quality = drops_service._get_streak_quality(days, test_config)
            assert quality == expected_quality
            print(f"[OK] Streak day {days} -> {expected_quality}")

    def test_streak_messages_requirement(self, drops_service, test_config):
        """Test that streak requires minimum messages"""
        # Create streak with insufficient messages
        for i in range(test_config.streak_messages_required - 1):
            drops_service.increment_viewer_message_count(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                viewer_id="viewer123",
                viewer_name="TestViewer",
            )

        streak = drops_service.get_user_streak(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
        )

        assert streak.messages_this_stream == test_config.streak_messages_required - 1
        print(
            f"[OK] Streak messages requirement tracking works: {streak.messages_this_stream}/{test_config.streak_messages_required}"
        )

    def test_streak_progression_uses_previous_stream_session(
        self, drops_service, test_config, test_rewards, db_session
    ):
        """Streak progression should be computed across stream_session boundaries."""
        drops_service._check_stream_online = lambda **kwargs: True
        session_service = StreamSessionService(drops_service.db)

        first_session = session_service.get_or_create_active_session(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
        )
        drops_service.update_user_streak(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
        )
        for _ in range(test_config.streak_messages_required):
            drops_service.increment_viewer_message_count(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                viewer_id="viewer123",
                viewer_name="TestViewer",
            )

        session_service.end_session(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
        )
        second_session = session_service.get_or_create_active_session(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
        )

        result = drops_service.process_streak_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            chat_message_id=101,
        )

        assert first_session.id != second_session.id
        assert result is not None
        assert result["type"] == "streak_pending"
        assert result["streak_days"] == 1
        assert result["stream_session_id"] == second_session.id
        assert result["source_event_id"] == "chat_message:101"

        streak = drops_service.get_user_streak(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
        )
        assert streak.current_streak == 1
        assert streak.last_stream_session_id == second_session.id

        pending = db_session.query(PendingStreakChest).filter_by(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            status="pending",
        ).first()
        assert pending is not None
        assert pending.stream_session_id == second_session.id
        assert pending.source_event_id == "chat_message:101"
        print("[OK] Streak progression uses previous stream session boundaries")

    def test_pending_streak_chest_upgrades_instead_of_duplicate(
        self, drops_service, test_config, db_session
    ):
        """A viewer keeps one pending streak chest that upgrades by quality."""
        drops_service._check_stream_online = lambda **kwargs: True
        test_config.streak_days_common = 7
        test_config.streak_days_rare = 7
        test_config.streak_days_epic = 7
        test_config.streak_days_legendary = 14
        db_session.commit()

        streak = UserStreak(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            current_streak=6,
            max_streak=6,
            messages_this_stream=test_config.streak_messages_required,
        )
        db_session.add(streak)
        db_session.commit()

        epic_result = drops_service.process_streak_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            source_event_id="event-7",
        )

        assert epic_result is not None
        assert epic_result["quality"] == "Epic"
        assert db_session.query(PendingStreakChest).filter_by(status="pending").count() == 1

        streak.current_streak = 13
        streak.max_streak = 13
        streak.last_stream_session_id = None
        streak.messages_this_stream = test_config.streak_messages_required
        db_session.commit()

        legendary_result = drops_service.process_streak_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            source_event_id="event-14",
        )

        pending = db_session.query(PendingStreakChest).filter_by(status="pending").one()
        assert legendary_result is not None
        assert legendary_result["quality"] == "Legendary"
        assert legendary_result["pending_chest_id"] == epic_result["pending_chest_id"]
        assert pending.quality_name == "Legendary"
        assert pending.streak_days == 14


class TestDonationDrops:
    """Test donation-triggered drops"""

    def test_donation_quality_determination(self, drops_service, test_config):
        """Test donation quality determination based on amount"""
        test_cases = [
            (50.0, "Common"),
            (100.0, "Rare"),
            (500.0, "Epic"),
            (1000.0, "Legendary"),
        ]

        for amount, expected_quality in test_cases:
            quality = drops_service._get_donation_quality(amount, test_config)
            assert quality == expected_quality
            print(f"[OK] Donation ${amount} -> {expected_quality}")

    def test_donation_drops_disabled(self, drops_service, test_config, db_session):
        """Test that donation drops can be disabled"""
        # Disable donation drops
        test_config.donation_enabled = False
        db_session.commit()

        result = drops_service.process_donation_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            donation_amount=100.0,
        )

        assert result is None
        print("[OK] Donation drops can be disabled")

    def test_donation_drops_enabled(self, drops_service, test_config, test_rewards):
        """Test that donation drops work when enabled"""
        result = drops_service.process_donation_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            donation_amount=100.0,
        )

        assert result is not None
        assert result["type"] == "donation"
        assert result["quality"] == "Rare"  # 100.0 = Rare
        assert result["donation_amount"] == 100.0
        print(f"[OK] Donation drops work: {result['reward']} ({result['quality']})")


class TestRewardCalculation:
    """Test reward calculation correctness"""

    def test_probability_validation(
        self, drops_calc_service, test_config, test_rewards
    ):
        """Test that probabilities are valid"""
        is_valid, error = drops_calc_service.validate_probabilities(
            user_id=1, channel_name="test_channel", quality_name="Common"
        )

        assert is_valid
        assert error is None
        print("[OK] Probability validation works")

    def test_get_probabilities(self, drops_calc_service, test_config, test_rewards):
        """Test getting probability distribution"""
        probabilities = drops_calc_service.get_probabilities(
            user_id=1, channel_name="test_channel", quality_name="Common"
        )

        assert len(probabilities) > 0
        total_prob = sum(probabilities.values())
        assert 0.99 <= total_prob <= 1.01  # Allow small floating point error
        print(
            f"[OK] Probability distribution works: {len(probabilities)} rewards, total={total_prob:.4f}"
        )

    def test_zero_weight_handling(self, drops_calc_service, test_config, db_session):
        """Test handling of zero-weight rewards"""
        # Create a new quality for this test
        new_quality = DropsQuality(
            id=10, name="TestQuality", color="#000000", weight=100
        )
        db_session.add(new_quality)
        db_session.commit()

        # Add rewards with zero weights
        for i in range(3):
            reward = DropsReward(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                name=f"Zero Weight Reward {i + 1}",
                quality_id=new_quality.id,
                weight=0,
                reward_type="points",
                reward_value="100",
                is_active=True,
            )
            db_session.add(reward)
        db_session.commit()

        is_valid, error = drops_calc_service.validate_probabilities(
            user_id=1, channel_name="test_channel", quality_name="TestQuality"
        )

        assert not is_valid
        assert (
            "invalid weights" in error.lower() or "total weight is 0" in error.lower()
        )
        print("[OK] Zero weight handling works")


class TestDropsHistory:
    """Test drops history recording"""

    def test_record_drops_history(self, drops_service, test_config, test_rewards):
        """Test that drops are recorded in history"""
        # Process a donation drop
        result = drops_service.process_donation_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            donation_amount=100.0,
        )

        assert result is not None

        # Check history
        history = drops_service.get_drops_history(
            user_id=1, channel_name="test_channel", platform="twitch", limit=10
        )

        assert len(history) > 0
        assert history[0].viewer_id == "viewer123"
        assert history[0].lootbox_type == "donation"
        print(f"[OK] Drops history recording works: {len(history)} entries")

    def test_drops_stats(self, drops_service, test_config, test_rewards):
        """Test drops statistics"""
        # Create some drops
        for i in range(5):
            drops_service.process_donation_drops(
                user_id=1,
                channel_name="test_channel",
                platform="twitch",
                viewer_id=f"viewer{i}",
                viewer_name=f"TestViewer{i}",
                donation_amount=100.0,
            )

        stats = drops_service.get_drops_stats(
            user_id=1, channel_name="test_channel", platform="twitch"
        )

        assert stats["totalDrops"] >= 5
        assert stats["total_drops"] == stats["totalDrops"]
        assert stats["today_drops"] == stats["todayDrops"]
        assert stats["legendary_drops"] == stats["legendaryDrops"]
        assert stats["mythical_drops"] == stats["mythicalDrops"]
        print(f"[OK] Drops stats work: {stats}")

    def test_donation_history_is_idempotent_by_source_event(
        self, drops_service, test_config, test_rewards
    ):
        """Duplicate donation events should not create duplicate rewards/history."""
        drops_service._check_stream_online = lambda **kwargs: True
        session_service = StreamSessionService(drops_service.db)
        active_session = session_service.get_or_create_active_session(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
        )

        first_result = drops_service.process_donation_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            donation_amount=100.0,
            donation_alert_id="alert-1",
        )
        second_result = drops_service.process_donation_drops(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer123",
            viewer_name="TestViewer",
            donation_amount=100.0,
            donation_alert_id="alert-1",
        )

        history = drops_service.get_drops_history(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            limit=10,
        )

        assert first_result is not None
        assert first_result["stream_session_id"] == active_session.id
        assert first_result["source_event_id"] == "donation_alert:alert-1"
        assert second_result is None
        assert len(history) == 1
        assert history[0].stream_session_id == active_session.id
        assert history[0].source_event_id == "donation_alert:alert-1"
        print("[OK] Donation drops are idempotent per source event")


class TestMythicalSessionRepository:
    """Regression tests for mythical session repository helpers."""

    def test_get_active_mythical_session_returns_record(self, db_session):
        now = utcnow_naive()
        session = MythicalDropsSession(
            user_id=1,
            session_id=None,
            channel_name="test_channel",
            platform="twitch",
            donation_amount=2000.0,
            window_duration_minutes=5,
            is_active=True,
            started_at=now,
            expires_at=now + timedelta(minutes=5),
        )
        db_session.add(session)
        db_session.commit()

        repo = DropsHistoryRepository(db_session)
        found = repo.get_active_mythical_session(
            channel_name="test_channel",
            now_time=now,
            user_id=1,
            session_id=None,
        )

        assert found is not None
        assert found.id == session.id

    def test_get_active_mythical_session_ignores_expired(self, db_session):
        now = utcnow_naive()
        expired = MythicalDropsSession(
            user_id=1,
            session_id=None,
            channel_name="test_channel",
            platform="twitch",
            donation_amount=2000.0,
            window_duration_minutes=5,
            is_active=True,
            started_at=now - timedelta(minutes=10),
            expires_at=now - timedelta(minutes=1),
        )
        db_session.add(expired)
        db_session.commit()

        repo = DropsHistoryRepository(db_session)
        found = repo.get_active_mythical_session(
            channel_name="test_channel",
            now_time=now,
            user_id=1,
            session_id=None,
        )

        assert found is None


class TestCrossPlatformRewards:
    """Test that rewards are cross-platform"""

    def test_rewards_available_on_all_platforms(
        self, drops_service, test_config, test_rewards
    ):
        """Test that rewards created for one platform are available on all platforms"""
        # Get rewards for Twitch
        twitch_rewards = drops_service.get_rewards(
            user_id=1, channel_name="test_channel", platform="twitch"
        )

        # Get rewards for VK
        vk_rewards = drops_service.get_rewards(
            user_id=1, channel_name="test_channel", platform="vk"
        )

        # Should be the same rewards (cross-platform)
        assert len(twitch_rewards) == len(vk_rewards)
        print(
            f"[OK] Cross-platform rewards work: {len(twitch_rewards)} rewards available on all platforms"
        )

    def test_user_only_dashboard_helpers(self, drops_service, test_config, test_rewards):
        """Dashboard-facing drops helpers should work through user-only APIs."""
        config = drops_service.get_user_config(user_id=1, channel_name="test_channel")
        assert config is not None
        assert config.user_id == 1
        assert config.platform == "global"

        updated = drops_service.create_or_update_user_config(
            user_id=1,
            channel_name="test_channel",
            config_data={"streak_messages_required": 7},
        )
        assert updated.streak_messages_required == 7

        rewards = drops_service.get_user_rewards(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
        )
        assert len(rewards) == len(test_rewards)

        reward = drops_service._get_random_user_reward(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            quality_id=1,
        )
        assert reward is not None
        assert reward.user_id == 1

        streak = drops_service.increment_viewer_message_count_for_user(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer-user-only",
            viewer_name="ViewerUserOnly",
        )
        assert streak is not None
        assert streak.user_id == 1
        assert streak.session_id is None

        donation_result = drops_service.process_donation_drops_for_user(
            user_id=1,
            channel_name="test_channel",
            platform="twitch",
            viewer_id="viewer-user-only",
            viewer_name="ViewerUserOnly",
            donation_amount=100.0,
        )
        assert donation_result is not None
        assert donation_result["type"] == "donation"


def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("DROPS SYSTEM FUNCTIONALITY TESTS")
    print("=" * 80 + "\n")

    # Run pytest
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_all_tests()
