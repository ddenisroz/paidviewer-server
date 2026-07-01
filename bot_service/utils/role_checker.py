"""Legacy role helpers used by older Twitch and VK chat flows."""

import logging
from typing import Any

logger = logging.getLogger("bot_service")


class RoleChecker:
    """Check user roles across supported chat platforms."""

    @staticmethod
    def check_twitch_role(user_badges: list[str], user_id: str, channel_owner_id: str) -> list[str]:
        """Return normalized Twitch roles from IRC badge data."""

        roles: list[str] = []

        for badge in user_badges:
            if badge == "broadcaster":
                roles.append("broadcaster")
            elif badge == "moderator":
                roles.append("moderator")
            elif badge == "subscriber":
                roles.append("subscriber")
            elif badge == "vip":
                roles.append("vip")
            elif badge == "founder":
                roles.append("founder")

        if user_id == channel_owner_id:
            roles.append("broadcaster")

        return list(set(roles))

    @staticmethod
    def check_vk_live_role(user_data: dict[str, Any]) -> list[str]:
        """Return normalized VK Live roles from upstream user data."""

        roles: list[str] = []

        if user_data.get("is_owner", False):
            roles.append("owner")

        if user_data.get("is_moderator", False):
            roles.append("moderator_vk")

        custom_roles = user_data.get("roles", [])
        for role in custom_roles:
            role_name = role.get("name", "").lower()
            if role_name:
                roles.append(f"custom_{role_name}")

        return roles

    @staticmethod
    def can_execute_command(user_roles: list[str], allowed_roles: str, platform: str) -> bool:
        """Return whether the user can execute a command for the platform."""

        if allowed_roles == "all":
            return True

        allowed_list = [role.strip() for role in allowed_roles.split(",")]

        for user_role in user_roles:
            if user_role in allowed_list:
                return True

        if platform == "twitch":
            if "moderator" in allowed_list and "broadcaster" in user_roles:
                return True
        elif platform == "vk":
            if "moderator_vk" in allowed_list and "owner" in user_roles:
                return True

        return False

    @staticmethod
    def get_user_role_display(user_roles: list[str], platform: str) -> str:
        """Return a human-readable role label for the platform."""

        if not user_roles:
            return "Viewer"

        if platform == "twitch":
            if "broadcaster" in user_roles:
                return "Broadcaster"
            if "moderator" in user_roles:
                return "Moderator"
            if "founder" in user_roles:
                return "Founder"
            if "vip" in user_roles:
                return "VIP"
            if "subscriber" in user_roles:
                return "Subscriber"
        elif platform == "vk":
            if "owner" in user_roles:
                return "Owner"
            if "moderator_vk" in user_roles:
                return "Moderator"

        custom_roles = [role for role in user_roles if role.startswith("custom_")]
        if custom_roles:
            return custom_roles[0].replace("custom_", "").title()

        return "Viewer"
