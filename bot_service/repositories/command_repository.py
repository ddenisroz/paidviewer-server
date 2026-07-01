# bot_service/repositories/command_repository.py
"""
Repository for BotCommand CRUD operations.
Following Clean Architecture - all database access is encapsulated here.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from repositories.base_repository import BaseRepository
from core.database import BotCommand, CommandInvocation


class CommandRepository(BaseRepository[BotCommand]):
    """
    Repository for BotCommand entities.
    Handles all database operations for commands (global, custom, overrides).
    """
    
    def __init__(self, db: Session):
        super().__init__(BotCommand, db)

    # === Global Commands ===

    def get_global_commands(self) -> List[BotCommand]:
        """Get all global commands (available to everyone)."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'global',
                BotCommand.user_id.is_(None)
            )
        ).all()

    # === User Custom Commands ===

    def get_user_custom_commands(self, user_id: int) -> List[BotCommand]:
        """Get user's custom commands."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'custom',
                BotCommand.user_id == user_id
            )
        ).all()

    def get_custom_commands_count(self, user_id: int) -> int:
        """Count user's custom commands."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'custom',
                BotCommand.user_id == user_id
            )
        ).count()

    # === User Overrides ===

    def get_user_overrides(self, user_id: int) -> List[BotCommand]:
        """Get user's command overrides."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'override',
                BotCommand.user_id == user_id
            )
        ).all()

    def get_override_by_name(self, command_name: str, user_id: int) -> Optional[BotCommand]:
        """Get specific override by command name for user."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'override',
                BotCommand.user_id == user_id,
                BotCommand.command_name == command_name
            )
        ).first()

    def get_override_by_alias(self, alias: str, user_id: int) -> Optional[BotCommand]:
        """Get override by alias."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'override',
                BotCommand.user_id == user_id,
                BotCommand.alias == alias
            )
        ).first()

    # === Command Lookup ===

    def find_command(
        self,
        command_name: str,
        user_id: int,
        platform: str
    ) -> Optional[BotCommand]:
        """
        Find command with priority: custom → override → custom alias → override alias → global.
        Returns the first matching enabled command.
        """
        # 1. Custom command
        custom_cmd = self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'custom',
                BotCommand.user_id == user_id,
                BotCommand.command_name == command_name,
                BotCommand.is_enabled == True
            )
        ).first()
        
        if custom_cmd and self._check_platform(custom_cmd, platform):
            return custom_cmd

        # 2. Override (allow disabled override to block global command)
        override_cmd = self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'override',
                BotCommand.user_id == user_id,
                BotCommand.command_name == command_name,
            )
        ).first()

        if override_cmd:
            if self._check_platform(override_cmd, platform):
                if not override_cmd.is_enabled:
                    return None
                return override_cmd

        # 3. Alias lookup for user custom commands
        custom_alias_cmd = self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'custom',
                BotCommand.user_id == user_id,
                BotCommand.alias == command_name,
                BotCommand.is_enabled == True
            )
        ).first()

        if custom_alias_cmd and self._check_platform(custom_alias_cmd, platform):
            return custom_alias_cmd

        # 4. Alias lookup for user overrides
        override_alias_cmd = self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'override',
                BotCommand.user_id == user_id,
                BotCommand.alias == command_name,
                BotCommand.is_enabled == True
            )
        ).first()
        
        if override_alias_cmd and self._check_platform(override_alias_cmd, platform):
            return override_alias_cmd

        # 5. Global command or built-in compat alias
        global_cmd = self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'global',
                BotCommand.user_id.is_(None),
                or_(BotCommand.command_name == command_name, BotCommand.alias == command_name),
                BotCommand.is_enabled == True
            )
        ).first()
        
        if global_cmd and self._check_platform(global_cmd, platform):
            return global_cmd

        return None

    def _check_platform(self, command: BotCommand, platform: str) -> bool:
        """Check if command is available on platform."""
        if not command.platforms:
            return True
        platforms = [p.strip().lower() for p in command.platforms.split(',')]
        return platform.lower() in platforms or 'all' in platforms

    # === Existence Checks ===

    def command_exists(self, command_name: str, user_id: int) -> bool:
        """Check if command with name exists for user."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_name == command_name,
                BotCommand.user_id == user_id
            )
        ).first() is not None

    def alias_exists(self, alias: str, user_id: int) -> bool:
        """Check if alias is already used by user."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.user_id == user_id,
                BotCommand.alias == alias
            )
        ).first() is not None

    def trigger_exists(self, trigger: str, user_id: int, exclude_command_id: Optional[int] = None) -> bool:
        """Check whether a command trigger or alias is already reserved for this user."""
        cleaned_trigger = (trigger or "").strip().lower()
        if not cleaned_trigger:
            return False

        query = self.db.query(BotCommand).filter(
            or_(
                and_(
                    BotCommand.command_type == 'global',
                    BotCommand.user_id.is_(None),
                    BotCommand.command_name == cleaned_trigger,
                ),
                and_(
                    BotCommand.user_id == user_id,
                    or_(
                        BotCommand.command_name == cleaned_trigger,
                        BotCommand.alias == cleaned_trigger,
                    ),
                ),
            )
        )
        if exclude_command_id is not None:
            query = query.filter(BotCommand.id != exclude_command_id)
        return query.first() is not None

    def get_global_command_by_name(self, command_name: str) -> Optional[BotCommand]:
        """Get global command by name."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.command_type == 'global',
                BotCommand.user_id.is_(None),
                BotCommand.command_name == command_name
            )
        ).first()

    # === CRUD Operations ===

    def get_by_id(self, command_id: int) -> Optional[BotCommand]:
        """Get command by ID."""
        return self.db.query(BotCommand).filter(BotCommand.id == command_id).first()

    def get_by_id_and_user(self, command_id: int, user_id: int) -> Optional[BotCommand]:
        """Get command by ID owned by user."""
        return self.db.query(BotCommand).filter(
            and_(
                BotCommand.id == command_id,
                BotCommand.user_id == user_id
            )
        ).first()

    def create_command(self, command: BotCommand) -> BotCommand:
        """Create a new command."""
        self.db.add(command)
        self.db.commit()
        self.db.refresh(command)
        return command

    def update_command(self, command: BotCommand) -> BotCommand:
        """Update existing command."""
        self.db.commit()
        self.db.refresh(command)
        return command

    def get_all_enabled_commands(self, user_id: int, platform: str) -> List[BotCommand]:
        """Get all enabled commands (global + custom/override) filtering by platform."""
        return self.db.query(BotCommand).filter(
            or_(
                BotCommand.command_type == 'global',
                BotCommand.user_id == user_id
            )
        ).filter(
            or_(
                BotCommand.platforms.like(f'%{platform}%'),
                BotCommand.platforms.like('%all%')
            )
        ).filter(
            BotCommand.is_enabled == True
        ).all()

    def get_command_history(
        self,
        user_id: int,
        platform: Optional[str] = None,
        command_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> List[BotCommand]:
        """Get recently used commands for user with optional filters."""
        query = self.db.query(BotCommand).filter(
            and_(
                BotCommand.user_id == user_id,
                or_(BotCommand.last_used.isnot(None), BotCommand.usage_count > 0),
            )
        )

        if platform:
            query = query.filter(
                or_(
                    BotCommand.platforms.like(f"%{platform}%"),
                    BotCommand.platforms.like("%all%"),
                )
            )

        if command_type and command_type != "all":
            query = query.filter(BotCommand.command_type == command_type)

        if search:
            pattern = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    BotCommand.command_name.ilike(pattern),
                    BotCommand.alias.ilike(pattern),
                    BotCommand.response_text.ilike(pattern),
                )
            )

        return (
            query.order_by(BotCommand.last_used.desc().nullslast(), BotCommand.usage_count.desc())
            .limit(max(1, min(limit, 300)))
            .all()
        )

    def create_invocation(
        self,
        *,
        user_id: int,
        command_id: Optional[int],
        canonical_command_name: str,
        used_trigger: str,
        platform: str,
        channel_name: Optional[str] = None,
        viewer_name: Optional[str] = None,
        viewer_id: Optional[str] = None,
        message_text: Optional[str] = None,
        chat_message_id: Optional[int] = None,
        status: str = "success",
        error: Optional[str] = None,
    ) -> CommandInvocation:
        """Persist one concrete command invocation."""
        invocation = CommandInvocation(
            user_id=user_id,
            command_id=command_id,
            canonical_command_name=(canonical_command_name or "").strip().lower(),
            used_trigger=(used_trigger or canonical_command_name or "").strip().lower(),
            platform=(platform or "").strip().lower(),
            channel_name=channel_name,
            viewer_name=viewer_name,
            viewer_id=str(viewer_id) if viewer_id is not None else None,
            message_text=message_text,
            chat_message_id=chat_message_id,
            status=status or "success",
            error=error,
        )
        self.db.add(invocation)
        return invocation

    def get_invocation_history(
        self,
        user_id: int,
        platform: Optional[str] = None,
        command_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> List[CommandInvocation]:
        """Get recent concrete command invocations for a user."""
        query = self.db.query(CommandInvocation).outerjoin(
            BotCommand,
            CommandInvocation.command_id == BotCommand.id,
        ).filter(CommandInvocation.user_id == user_id)

        if platform:
            query = query.filter(CommandInvocation.platform == platform)

        if command_type and command_type != "all":
            query = query.filter(BotCommand.command_type == command_type)

        if search:
            pattern = f"%{search.strip().lower()}%"
            query = query.filter(
                or_(
                    CommandInvocation.canonical_command_name.ilike(pattern),
                    CommandInvocation.used_trigger.ilike(pattern),
                    CommandInvocation.viewer_name.ilike(pattern),
                    CommandInvocation.message_text.ilike(pattern),
                )
            )

        return (
            query.order_by(CommandInvocation.created_at.desc().nullslast(), CommandInvocation.id.desc())
            .limit(max(1, min(limit, 300)))
            .all()
        )
        
    def delete_command(self, command: BotCommand) -> None:
        """Delete command."""
        self.db.delete(command)
        self.db.commit()
