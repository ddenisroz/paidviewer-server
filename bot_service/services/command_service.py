# bot_service/services/command_service.py
"""
Service for command management, permissions and cooldowns.
Following Clean Architecture - business logic only, no direct DB access.
"""
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from core.database import BotCommand, User
from core.permissions import PlatformRole, PLATFORM_ROLE_HIERARCHY, get_platform_roles
from repositories.command_repository import CommandRepository
from services.command_cooldown_store import CommandCooldownStore, get_command_cooldown_store
from validators.input_validators import sanitize_input

logger = logging.getLogger('bot_service')


class CommandService:
    """
    Service for managing commands, permissions, and cooldowns.

    Uses the repository pattern for data access.
    """

    def __init__(
        self,
        command_repo: Optional[CommandRepository] = None,
        cooldown_store: Optional[CommandCooldownStore] = None,
    ):
        """
        Initialize CommandService.
        
        Args:
            command_repo: Optional CommandRepository instance. If not provided,
                          methods that need it will require db session.
        """
        self.logger = logger
        self._command_repo = command_repo
        self._cooldown_store = cooldown_store or get_command_cooldown_store()

    def _get_repo(self, db: Session) -> CommandRepository:
        """Get repository instance, creating one if needed."""
        if self._command_repo:
            return self._command_repo
        return CommandRepository(db)

    @staticmethod
    def _sanitize_command_trigger(value: str, *, field_name: str = "command") -> str:
        trigger = sanitize_input((value or "").strip().lstrip("!").lower(), max_length=50, allow_special=False)
        if not trigger:
            raise ValueError(f"{field_name} cannot be empty")
        return trigger

    # === Query Methods ===

    def find_command(
        self,
        command_name: str,
        user_id: int,
        channel_name: str,
        platform: str,
        db: Session
    ) -> Optional[BotCommand]:
        """
        Find a command using priority: custom -> override -> global.
        """
        try:
            repo = self._get_repo(db)
            command = repo.find_command(command_name, user_id, platform)
            
            if command:
                cmd_type = command.command_type.upper()
                if command.alias and command.alias == command_name:
                    self.logger.debug(f"[CommandService] Found ALIAS: {command_name} -> {command.command_name}")
                else:
                    self.logger.debug(f"[CommandService] Found {cmd_type}: {command_name}")
            
            return command

        except Exception:
            self.logger.exception("Error finding command")
            return None

    def get_all_commands_for_user(
        self,
        user_id: Optional[int],
        db: Session
    ) -> Dict[str, Any]:
        """
        Get all commands for user (global + overrides + custom).
        
        Args:
            user_id: User ID or None for anonymous/public access
            db: Database session
            
        Returns:
            Dict with global_commands, override_commands, basic_commands, custom_commands
        """
        try:
            repo = self._get_repo(db)
            is_public_request = user_id is None or user_id == -1
            
            # 1. Global commands (available to everyone)
            global_commands = repo.get_global_commands()
            
            # 2. Anonymous/public access gets only global commands.
            if is_public_request:
                override_commands = []
                custom_commands = []
            else:
                override_commands = repo.get_user_overrides(user_id)
                custom_commands = repo.get_user_custom_commands(user_id)
            
            # Convert to dicts
            global_commands_data = [self._command_to_dict(cmd) for cmd in global_commands]
            override_commands_data = [self._command_to_dict(cmd) for cmd in override_commands]
            custom_commands_data = [self._command_to_dict(cmd) for cmd in custom_commands]
            
            # Merge global + overrides into basic_commands
            basic_commands_dict = {}
            for cmd_data in global_commands_data:
                basic_commands_dict[cmd_data["command_name"]] = cmd_data
            
            for cmd_data in override_commands_data:
                parent_cmd = next(
                    (g for g in global_commands_data if g["id"] == cmd_data["parent_command_id"]),
                    None
                )
                if parent_cmd:
                    basic_commands_dict[parent_cmd["command_name"]] = cmd_data
            
            basic_commands_data = list(basic_commands_dict.values())
            
            self.logger.info(
                f"[OK] Returned {len(global_commands_data)} global + "
                f"{len(override_commands_data)} overrides + "
                f"{len(basic_commands_data)} merged basic + "
                f"{len(custom_commands_data)} custom commands"
            )
            
            return {
                "success": True,
                "global_commands": global_commands_data,
                "override_commands": override_commands_data,
                "basic_commands": basic_commands_data,
                "custom_commands": custom_commands_data
            }
            
        except Exception:
            self.logger.exception("Error getting commands")
            raise

    def _command_to_dict(self, cmd: BotCommand) -> Dict[str, Any]:
        """Convert command to dictionary."""
        tags = []
        if cmd.tags:
            if ',' in cmd.tags:
                tags = [tag.strip() for tag in cmd.tags.split(',') if tag.strip()]
            else:
                tags = [cmd.tags.strip()]

        return {
            "id": cmd.id,
            "command_name": cmd.command_name,
            "response_text": cmd.response_text or "",
            "platforms": cmd.platforms or "twitch,vk",
            "allowed_roles": cmd.allowed_roles or "all",
            "cooldown_seconds": cmd.cooldown_seconds or 0,
            "is_enabled": cmd.is_enabled,
            "description": cmd.description,
            "command_type": cmd.command_type,
            "parent_command_id": cmd.parent_command_id,
            "alias": cmd.alias,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
            "updated_at": cmd.updated_at.isoformat() if cmd.updated_at else None,
            "last_used": cmd.last_used.isoformat() if cmd.last_used else None,
            "usage_count": cmd.usage_count or 0,
            "tags": tags,
            "extra_settings": cmd.extra_settings or {}
        }

    def get_command_history(
        self,
        user_id: int,
        platform: Optional[str],
        command_type: Optional[str],
        search: Optional[str],
        limit: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Return concrete command invocation history for the user."""
        repo = self._get_repo(db)
        invocations = repo.get_invocation_history(
            user_id=user_id,
            platform=platform,
            command_type=command_type,
            search=search,
            limit=limit,
        )
        return {
            "success": True,
            "data": [self._invocation_to_dict(item) for item in invocations],
        }

    @staticmethod
    def _invocation_to_dict(invocation: Any) -> Dict[str, Any]:
        """Convert invocation history row to API shape."""
        return {
            "id": invocation.id,
            "command_id": invocation.command_id,
            "canonical_command_name": invocation.canonical_command_name,
            "used_trigger": invocation.used_trigger,
            "viewer_name": invocation.viewer_name,
            "viewer_id": invocation.viewer_id,
            "platform": invocation.platform,
            "channel_name": invocation.channel_name,
            "message_text": invocation.message_text,
            "chat_message_id": invocation.chat_message_id,
            "has_platform_message": bool(invocation.message_text or invocation.chat_message_id),
            "status": invocation.status,
            "error": invocation.error,
            "created_at": invocation.created_at.isoformat() if invocation.created_at else None,
        }

    # === CRUD Methods ===

    def create_custom_command(
        self,
        user_id: int,
        command_name: str,
        response_text: str,
        platforms: str = "twitch,vk",
        allowed_roles: str = "all",
        cooldown_seconds: int = 0,
        is_enabled: bool = True,
        extra_settings: Optional[Dict[str, Any]] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Create a new custom command.
        
        Raises:
            ValueError: If validation fails or limit reached
        """
        repo = self._get_repo(db)
        
        # Check custom commands limit (max 5)
        custom_count = repo.get_custom_commands_count(user_id)
        if custom_count >= 5:
            raise ValueError(
                "Custom command limit reached (maximum 5). "
                "Delete unused commands before creating new ones."
            )
        
        sanitized_name = self._sanitize_command_trigger(command_name, field_name="Command name")

        # Check if command exists globally, as a user command, or as a user alias.
        if repo.trigger_exists(sanitized_name, user_id):
            raise ValueError("A command with this name already exists")
        
        # Sanitize input
        sanitized_response = sanitize_input(response_text, max_length=1000, allow_special=False)
        
        # Create command
        new_command = BotCommand(
            user_id=user_id,
            channel_name="default",
            command_name=sanitized_name,
            command_type="custom",
            response_text=sanitized_response,
            platforms=platforms,
            allowed_roles=allowed_roles,
            cooldown_seconds=cooldown_seconds,
            is_enabled=is_enabled,
            extra_settings=extra_settings or {}
        )
        
        created = repo.create_command(new_command)
        
        return {
            "success": True,
            "message": "Command created successfully",
            "data": {
                "id": created.id,
                "command_name": created.command_name
            }
        }

    def update_command(
        self,
        command_id: int,
        user_id: int,
        update_data: Dict[str, Any],
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Update an existing command.
        
        Raises:
            ValueError: If command not found or no permission
        """
        repo = self._get_repo(db)
        
        command = repo.get_by_id(command_id)
        if not command:
            raise ValueError("Command not found")
        
        # Check permissions
        if command.command_type == "global":
            raise ValueError("Global commands cannot be edited. Create an override instead.")

        if command.user_id != user_id:
            raise ValueError("No permission to edit this command")

        if "command_name" in update_data and update_data["command_name"] is not None:
            if command.command_type != "custom":
                raise ValueError("Only custom commands can be renamed. Use alias for global commands.")
            new_name = self._sanitize_command_trigger(update_data["command_name"], field_name="Command name")
            if new_name != command.command_name:
                if repo.trigger_exists(new_name, user_id, exclude_command_id=command.id):
                    raise ValueError("A command with this name already exists")
                command.command_name = new_name

        if "alias" in update_data:
            raw_alias = update_data.get("alias")
            if raw_alias is None or str(raw_alias).strip() == "":
                command.alias = None
            else:
                new_alias = self._sanitize_command_trigger(str(raw_alias), field_name="Alias")
                if repo.trigger_exists(new_alias, user_id, exclude_command_id=command.id):
                    raise ValueError("Alias is already in use")
                command.alias = new_alias
        
        # Update fields
        if "is_enabled" in update_data and update_data["is_enabled"] is not None:
            command.is_enabled = update_data["is_enabled"]
        if "platforms" in update_data and update_data["platforms"] is not None:
            command.platforms = update_data["platforms"]
        if "allowed_roles" in update_data and update_data["allowed_roles"] is not None:
            command.allowed_roles = update_data["allowed_roles"]
        if "cooldown_seconds" in update_data and update_data["cooldown_seconds"] is not None:
            command.cooldown_seconds = update_data["cooldown_seconds"]
        if "response_text" in update_data and update_data["response_text"] is not None:
            command.response_text = sanitize_input(
                update_data["response_text"],
                max_length=1000,
                allow_special=False
            )
        if "extra_settings" in update_data and update_data["extra_settings"] is not None:
            command.extra_settings = update_data["extra_settings"]
        
        repo.update_command(command)
        
        return {"success": True, "message": "Command updated successfully"}

    def create_command_override(
        self,
        user_id: int,
        command_name: str,
        alias: Optional[str] = None,
        platforms: Optional[str] = None,
        allowed_roles: Optional[str] = None,
        cooldown_seconds: Optional[int] = None,
        is_enabled: bool = True,
        extra_settings: Optional[Dict[str, Any]] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Create user override for a global command.
        
        Raises:
            ValueError: If validation fails
        """
        repo = self._get_repo(db)
        command_name = self._sanitize_command_trigger(command_name, field_name="Command name")
        
        # Check global command exists
        global_command = repo.get_global_command_by_name(command_name)
        if not global_command:
            raise ValueError(f"Global command '{command_name}' not found")
        
        # Check for existing override - update it if exists
        existing_override = repo.get_override_by_name(command_name, user_id)
        if existing_override:
            # Update existing override instead of error
            if platforms is not None:
                existing_override.platforms = platforms
            if allowed_roles is not None:
                existing_override.allowed_roles = allowed_roles
            if cooldown_seconds is not None:
                existing_override.cooldown_seconds = cooldown_seconds
            if is_enabled is not None:
                existing_override.is_enabled = is_enabled
            if extra_settings is not None:
                existing_override.extra_settings = extra_settings
            if alias is not None:
                if str(alias).strip():
                    cleaned_alias = self._sanitize_command_trigger(alias, field_name="Alias")
                    if repo.trigger_exists(cleaned_alias, user_id, exclude_command_id=existing_override.id):
                        raise ValueError(f"Alias '{cleaned_alias}' is already in use")
                    existing_override.alias = cleaned_alias
                else:
                    existing_override.alias = None
            
            db.commit()
            db.refresh(existing_override)
            
            self.logger.info(f"[OK] Updated existing override for command '{command_name}' by user {user_id}")
            
            return {
                "success": True,
                "message": f"Override for command '{command_name}' updated",
                "data": {
                    "id": existing_override.id,
                    "command_name": existing_override.command_name,
                    "alias": existing_override.alias,
                    "parent_command_id": existing_override.parent_command_id,
                    "extra_settings": existing_override.extra_settings
                }
            }
        
        cleaned_alias = None
        if alias is not None and str(alias).strip():
            cleaned_alias = self._sanitize_command_trigger(alias, field_name="Alias")
            if repo.trigger_exists(cleaned_alias, user_id):
                raise ValueError(f"Alias '{cleaned_alias}' is already in use")
        
        # Create override
        new_override = BotCommand(
            user_id=user_id,
            channel_name=None,
            command_name=command_name,
            command_type='override',
            parent_command_id=global_command.id,
            alias=cleaned_alias,
            response_text="",
            is_enabled=is_enabled,
            platforms=platforms if platforms else global_command.platforms,
            allowed_roles=allowed_roles if allowed_roles else global_command.allowed_roles,
            cooldown_seconds=cooldown_seconds if cooldown_seconds is not None else global_command.cooldown_seconds,
            tags=global_command.tags,
            description=global_command.description,
            extra_settings=extra_settings or {}
        )
        
        created = repo.create_command(new_override)
        
        self.logger.info(f"[OK] Created override for command '{command_name}' by user {user_id}")
        
        return {
            "success": True,
            "message": f"Override for command '{command_name}' created successfully",
            "data": {
                "id": created.id,
                "command_name": created.command_name,
                "alias": created.alias,
                "parent_command_id": created.parent_command_id,
                "extra_settings": created.extra_settings
            }
        }

    def delete_command(
        self,
        command_id: int,
        user_id: int,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Delete a command.
        
        Raises:
            ValueError: If command not found or no permission
        """
        repo = self._get_repo(db)
        
        command = repo.get_by_id(command_id)
        if not command:
            raise ValueError("Command not found")
        
        # Check permissions
        if command.command_type == "basic":
            raise ValueError("Base command cannot be deleted")

        if command.user_id != user_id:
            raise ValueError("No permission to delete this command")
        
        repo.delete_command(command)
        
        return {"success": True, "message": "Command deleted successfully"}

    # === Permission & Cooldown Methods ===

    def check_permission(
        self,
        command: BotCommand,
        user: User,
        platform: str,
        user_roles: List[str] = None
    ) -> bool:
        """
        Check whether the user can execute the command.
        """
        try:
            if not command.allowed_roles or command.allowed_roles.strip() == '':
                return True

            allowed_roles = [r.strip().lower() for r in command.allowed_roles.split(',')]

            if 'all' in allowed_roles or 'everyone' in allowed_roles:
                return True

            current_roles = user_roles or []
            if user:
               current_roles = get_platform_roles(user, platform)

            user_level = 1  # Default: viewer
            
            def get_role_level(role_val):
                if hasattr(role_val, 'value'):
                    role_str = role_val.value
                elif isinstance(role_val, str):
                    role_str = role_val
                else:
                    return 1
                 
                role_str = role_str.lower()
                if role_str in ['broadcaster', 'owner']:
                    r = PlatformRole.BROADCASTER
                elif role_str in ['moderator', 'mod']:
                    r = PlatformRole.MODERATOR
                elif role_str == 'vip':
                    r = PlatformRole.VIP
                elif role_str in ['subscriber', 'sub']:
                    r = PlatformRole.SUBSCRIBER
                else:
                    r = PlatformRole.VIEWER
                return PLATFORM_ROLE_HIERARCHY.get(r, 1)

            for role in current_roles:
                user_level = max(user_level, get_role_level(role))

            required_level = 1
            for role_str in allowed_roles:
                required_level = max(required_level, get_role_level(role_str))

            has_permission = user_level >= required_level

            if not has_permission:
                self.logger.debug(
                    f"Permission denied for '{command.command_name}': "
                    f"requires level {required_level}, user has level {user_level}"
                )

            return has_permission

        except Exception:
            self.logger.exception("Error checking permission")
            return False

    def check_cooldown(self, command: BotCommand, user_id: str) -> bool:
        """Check the command cooldown."""
        try:
            return self._cooldown_store.is_available(command, user_id)

        except Exception:
            self.logger.exception("Error checking cooldown")
            return True

    def update_cooldown(self, command: BotCommand, user_id: str):
        """Update cooldown after command execution."""
        try:
            self._cooldown_store.mark_used(command, user_id)

        except Exception:
            self.logger.exception("Error updating cooldown")

    def get_command_response(self, command: BotCommand) -> str:
        """Return the command response text."""
        return command.response_text or ""

