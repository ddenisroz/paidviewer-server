# bot_service/tests/test_command_repository.py
"""
Tests for CommandRepository.
Tests CRUD operations following Clean Architecture principles.
"""
import pytest
from sqlalchemy.orm import Session

from repositories.command_repository import CommandRepository
from core.database import BotCommand


class TestCommandRepository:
    """Tests for CommandRepository."""

    # === Global Commands ===

    def test_get_global_commands_empty(self, db: Session):
        """Should return empty list when no global commands exist."""
        repo = CommandRepository(db)
        result = repo.get_global_commands()
        assert result == []

    def test_get_global_commands(self, db: Session):
        """Should return all global commands."""
        repo = CommandRepository(db)
        
        # Create global commands
        cmd1 = BotCommand(
            command_name="help",
            command_type="global",
            user_id=None,
            response_text="Help text",
            is_enabled=True
        )
        cmd2 = BotCommand(
            command_name="about",
            command_type="global",
            user_id=None,
            response_text="About text",
            is_enabled=True
        )
        db.add_all([cmd1, cmd2])
        db.commit()
        
        result = repo.get_global_commands()
        
        assert len(result) == 2
        assert all(c.command_type == "global" for c in result)

    # === User Custom Commands ===

    def test_get_user_custom_commands_empty(self, db: Session, test_user):
        """Should return empty list when user has no custom commands."""
        repo = CommandRepository(db)
        result = repo.get_user_custom_commands(test_user.id)
        assert result == []

    def test_get_user_custom_commands(self, db: Session, test_user):
        """Should return user's custom commands."""
        repo = CommandRepository(db)
        
        cmd = BotCommand(
            command_name="mycommand",
            command_type="custom",
            user_id=test_user.id,
            response_text="My response",
            is_enabled=True
        )
        db.add(cmd)
        db.commit()
        
        result = repo.get_user_custom_commands(test_user.id)
        
        assert len(result) == 1
        assert result[0].command_name == "mycommand"

    def test_get_custom_commands_count(self, db: Session, test_user):
        """Should count user's custom commands."""
        repo = CommandRepository(db)
        
        # Initially 0
        assert repo.get_custom_commands_count(test_user.id) == 0
        
        # Add 2 commands
        for i in range(2):
            cmd = BotCommand(
                command_name=f"cmd{i}",
                command_type="custom",
                user_id=test_user.id,
                response_text=f"Response {i}",
                is_enabled=True
            )
            db.add(cmd)
        db.commit()
        
        assert repo.get_custom_commands_count(test_user.id) == 2

    # === User Overrides ===

    def test_get_user_overrides(self, db: Session, test_user):
        """Should return user's command overrides."""
        repo = CommandRepository(db)
        
        # Create global command first
        global_cmd = BotCommand(
            command_name="help",
            command_type="global",
            user_id=None,
            response_text="Help",
            is_enabled=True
        )
        db.add(global_cmd)
        db.commit()
        
        # Create override
        override = BotCommand(
            command_name="help",
            command_type="override",
            user_id=test_user.id,
            parent_command_id=global_cmd.id,
            response_text="",
            is_enabled=False  # User disabled the command
        )
        db.add(override)
        db.commit()
        
        result = repo.get_user_overrides(test_user.id)
        
        assert len(result) == 1
        assert result[0].command_type == "override"

    # === Find Command ===

    def test_find_command_custom_priority(self, db: Session, test_user):
        """Custom command should have highest priority."""
        repo = CommandRepository(db)
        
        # Create global
        db.add(BotCommand(
            command_name="test",
            command_type="global",
            user_id=None,
            response_text="Global",
            is_enabled=True,
            platforms="all"
        ))
        
        # Create custom with same name
        db.add(BotCommand(
            command_name="test",
            command_type="custom",
            user_id=test_user.id,
            response_text="Custom",
            is_enabled=True,
            platforms="all"
        ))
        db.commit()
        
        result = repo.find_command("test", test_user.id, "twitch")
        
        assert result is not None
        assert result.command_type == "custom"
        assert result.response_text == "Custom"

    def test_find_command_global_fallback(self, db: Session, test_user):
        """Should fallback to global when no custom/override exists."""
        repo = CommandRepository(db)
        
        db.add(BotCommand(
            command_name="help",
            command_type="global",
            user_id=None,
            response_text="Global help",
            is_enabled=True,
            platforms="all"
        ))
        db.commit()
        
        result = repo.find_command("help", test_user.id, "twitch")
        
        assert result is not None
        assert result.command_type == "global"

    def test_find_command_not_found(self, db: Session, test_user):
        """Should return None when command doesn't exist."""
        repo = CommandRepository(db)
        result = repo.find_command("nonexistent", test_user.id, "twitch")
        assert result is None

    def test_find_command_disabled(self, db: Session, test_user):
        """Should not find disabled commands."""
        repo = CommandRepository(db)
        
        db.add(BotCommand(
            command_name="disabled",
            command_type="global",
            user_id=None,
            response_text="Disabled",
            is_enabled=False,  # Disabled!
            platforms="all"
        ))
        db.commit()
        
        result = repo.find_command("disabled", test_user.id, "twitch")
        assert result is None

    def test_find_command_platform_filter(self, db: Session, test_user):
        """Should respect platform filter."""
        repo = CommandRepository(db)
        
        db.add(BotCommand(
            command_name="twitchonly",
            command_type="global",
            user_id=None,
            response_text="Twitch only",
            is_enabled=True,
            platforms="twitch"  # Only twitch!
        ))
        db.commit()
        
        # Should find on twitch
        result = repo.find_command("twitchonly", test_user.id, "twitch")
        assert result is not None
        
        # Should NOT find on vk
        result = repo.find_command("twitchonly", test_user.id, "vk")
        assert result is None

    def test_find_command_by_alias(self, db: Session, test_user):
        """Should find command by alias."""
        repo = CommandRepository(db)
        
        # Create global
        global_cmd = BotCommand(
            command_name="songrequest",
            command_type="global",
            user_id=None,
            response_text="Request song",
            is_enabled=True,
            platforms="all"
        )
        db.add(global_cmd)
        db.commit()
        
        # Create override with alias
        override = BotCommand(
            command_name="songrequest",
            command_type="override",
            user_id=test_user.id,
            parent_command_id=global_cmd.id,
            alias="sr",  # Alias!
            response_text="",
            is_enabled=True,
            platforms="all"
        )
        db.add(override)
        db.commit()
        
        # Find by alias
        result = repo.find_command("sr", test_user.id, "twitch")
        
        assert result is not None
        assert result.alias == "sr"
        assert result.command_name == "songrequest"

    def test_find_custom_command_by_alias(self, db: Session, test_user):
        """Should find custom command by optional alias."""
        repo = CommandRepository(db)

        db.add(BotCommand(
            command_name="main",
            command_type="custom",
            user_id=test_user.id,
            alias="extra",
            response_text="Hello",
            is_enabled=True,
            platforms="all",
        ))
        db.commit()

        result = repo.find_command("extra", test_user.id, "twitch")

        assert result is not None
        assert result.command_name == "main"
        assert result.alias == "extra"

    def test_command_invocation_history(self, db: Session, test_user):
        """Should store and return concrete command usage events."""
        repo = CommandRepository(db)
        cmd = BotCommand(
            command_name="hello",
            command_type="custom",
            user_id=test_user.id,
            response_text="Hi",
            is_enabled=True,
            platforms="all",
        )
        db.add(cmd)
        db.commit()

        repo.create_invocation(
            user_id=test_user.id,
            command_id=cmd.id,
            canonical_command_name="hello",
            used_trigger="hi",
            platform="twitch",
            channel_name="demo",
            viewer_name="Viewer",
            viewer_id="123",
            message_text="!hi there",
        )
        db.commit()

        history = repo.get_invocation_history(test_user.id)

        assert len(history) == 1
        assert history[0].canonical_command_name == "hello"
        assert history[0].used_trigger == "hi"
        assert history[0].viewer_name == "Viewer"
        assert history[0].message_text == "!hi there"

    # === Existence Checks ===

    def test_command_exists(self, db: Session, test_user):
        """Should check if command exists for user."""
        repo = CommandRepository(db)
        
        assert repo.command_exists("mycommand", test_user.id) is False
        
        db.add(BotCommand(
            command_name="mycommand",
            command_type="custom",
            user_id=test_user.id,
            response_text="Test",
            is_enabled=True
        ))
        db.commit()
        
        assert repo.command_exists("mycommand", test_user.id) is True

    def test_alias_exists(self, db: Session, test_user):
        """Should check if alias is used."""
        repo = CommandRepository(db)
        
        assert repo.alias_exists("sr", test_user.id) is False
        
        db.add(BotCommand(
            command_name="songrequest",
            command_type="override",
            user_id=test_user.id,
            alias="sr",
            response_text="",
            is_enabled=True
        ))
        db.commit()
        
        assert repo.alias_exists("sr", test_user.id) is True

    # === CRUD Operations ===

    def test_create_command(self, db: Session, test_user):
        """Should create new command."""
        repo = CommandRepository(db)
        
        new_cmd = BotCommand(
            command_name="newcmd",
            command_type="custom",
            user_id=test_user.id,
            response_text="New command",
            is_enabled=True
        )
        
        created = repo.create_command(new_cmd)
        
        assert created.id is not None
        assert created.command_name == "newcmd"
        
        # Verify in DB
        found = repo.get_by_id(created.id)
        assert found is not None

    def test_update_command(self, db: Session, test_user):
        """Should update command."""
        repo = CommandRepository(db)
        
        cmd = BotCommand(
            command_name="updateme",
            command_type="custom",
            user_id=test_user.id,
            response_text="Original",
            is_enabled=True
        )
        db.add(cmd)
        db.commit()
        
        # Update
        cmd.response_text = "Updated"
        cmd.is_enabled = False
        repo.update_command(cmd)
        
        # Verify
        found = repo.get_by_id(cmd.id)
        assert found.response_text == "Updated"
        assert found.is_enabled is False

    def test_delete_command(self, db: Session, test_user):
        """Should delete command."""
        repo = CommandRepository(db)
        
        cmd = BotCommand(
            command_name="deleteme",
            command_type="custom",
            user_id=test_user.id,
            response_text="Delete me",
            is_enabled=True
        )
        db.add(cmd)
        db.commit()
        cmd_id = cmd.id
        
        # Delete
        repo.delete_command(cmd)
        
        # Verify
        found = repo.get_by_id(cmd_id)
        assert found is None

    def test_get_by_id(self, db: Session, test_user):
        """Should get command by ID."""
        repo = CommandRepository(db)
        
        cmd = BotCommand(
            command_name="findme",
            command_type="custom",
            user_id=test_user.id,
            response_text="Find me",
            is_enabled=True
        )
        db.add(cmd)
        db.commit()
        
        found = repo.get_by_id(cmd.id)
        
        assert found is not None
        assert found.command_name == "findme"

    def test_get_by_id_and_user(self, db: Session, test_user, admin_user):
        """Should get command only if owned by user."""
        repo = CommandRepository(db)
        
        cmd = BotCommand(
            command_name="owned",
            command_type="custom",
            user_id=test_user.id,
            response_text="Owned",
            is_enabled=True
        )
        db.add(cmd)
        db.commit()
        
        # Should find for owner
        found = repo.get_by_id_and_user(cmd.id, test_user.id)
        assert found is not None
        
        # Should NOT find for other user
        found = repo.get_by_id_and_user(cmd.id, admin_user.id)
        assert found is None
