"""Test permission and role system."""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPermissionSystem:
    """Test suite for permission system."""

    def test_app_roles_defined(self):
        from core.permissions import AppRole

        assert hasattr(AppRole, "ADMIN")
        assert hasattr(AppRole, "USER")
        assert AppRole.ADMIN.value == "admin"
        assert AppRole.USER.value == "user"

    def test_permissions_defined(self):
        from core.permissions import Permission

        assert hasattr(Permission, "MANAGE_USERS")
        assert hasattr(Permission, "MANAGE_GLOBAL_VOICES")
        assert hasattr(Permission, "VIEW_ALL_SETTINGS")
        assert hasattr(Permission, "MANAGE_SYSTEM")
        assert hasattr(Permission, "BLOCK_USERS")
        assert hasattr(Permission, "MANAGE_OWN_SETTINGS")
        assert hasattr(Permission, "MANAGE_OWN_VOICES")
        assert hasattr(Permission, "MANAGE_STREAM")
        assert hasattr(Permission, "MANAGE_BOTS")
        assert hasattr(Permission, "MANAGE_COMMANDS")
        assert hasattr(Permission, "MANAGE_REWARDS")
        assert hasattr(Permission, "MANAGE_DROPS")
        assert hasattr(Permission, "VIEW_CHAT")
        assert hasattr(Permission, "VIEW_PUBLIC_DATA")

    def test_platform_roles_defined(self):
        from core.permissions import PlatformRole

        assert hasattr(PlatformRole, "BROADCASTER")
        assert hasattr(PlatformRole, "MODERATOR")
        assert hasattr(PlatformRole, "VIP")
        assert hasattr(PlatformRole, "SUBSCRIBER")
        assert hasattr(PlatformRole, "VIEWER")
        assert hasattr(PlatformRole, "OWNER")

    def test_admin_has_all_permissions(self):
        from core.permissions import AppRole, Permission, has_permission

        for permission in Permission:
            assert has_permission(AppRole.ADMIN, permission), f"Admin missing permission: {permission.value}"

    def test_user_has_correct_permissions(self):
        from core.permissions import AppRole, Permission, has_permission

        user_permissions = [
            Permission.MANAGE_OWN_SETTINGS,
            Permission.MANAGE_OWN_VOICES,
            Permission.MANAGE_STREAM,
            Permission.MANAGE_BOTS,
            Permission.MANAGE_COMMANDS,
            Permission.MANAGE_REWARDS,
            Permission.MANAGE_DROPS,
            Permission.VIEW_CHAT,
            Permission.VIEW_PUBLIC_DATA,
        ]
        for permission in user_permissions:
            assert has_permission(AppRole.USER, permission), f"User missing permission: {permission.value}"

        admin_only_permissions = [
            Permission.MANAGE_USERS,
            Permission.MANAGE_GLOBAL_VOICES,
            Permission.VIEW_ALL_SETTINGS,
            Permission.MANAGE_SYSTEM,
            Permission.BLOCK_USERS,
        ]
        for permission in admin_only_permissions:
            assert not has_permission(AppRole.USER, permission), f"User should not have permission: {permission.value}"

    def test_platform_role_hierarchy(self):
        from core.permissions import PLATFORM_ROLE_HIERARCHY, PlatformRole

        assert PLATFORM_ROLE_HIERARCHY[PlatformRole.BROADCASTER] == 5
        assert PLATFORM_ROLE_HIERARCHY[PlatformRole.OWNER] == 5
        assert PLATFORM_ROLE_HIERARCHY[PlatformRole.MODERATOR] == 4
        assert PLATFORM_ROLE_HIERARCHY[PlatformRole.VIP] == 3
        assert PLATFORM_ROLE_HIERARCHY[PlatformRole.SUBSCRIBER] == 2
        assert PLATFORM_ROLE_HIERARCHY[PlatformRole.VIEWER] == 1

    def test_get_platform_roles_twitch(self):
        from core.permissions import PlatformRole, get_platform_roles

        user = Mock()
        user.twitch_is_broadcaster = True
        user.twitch_is_moderator = False
        user.twitch_is_vip = False
        user.twitch_is_subscriber = True

        roles = get_platform_roles(user, "twitch")
        assert PlatformRole.VIEWER in roles
        assert PlatformRole.BROADCASTER in roles
        assert PlatformRole.SUBSCRIBER in roles
        assert PlatformRole.MODERATOR not in roles
        assert PlatformRole.VIP not in roles

    def test_get_platform_roles_vk(self):
        from core.permissions import PlatformRole, get_platform_roles

        user = Mock()
        user.vk_is_owner = False
        user.vk_is_moderator = True

        roles = get_platform_roles(user, "vk")
        assert PlatformRole.VIEWER in roles
        assert PlatformRole.MODERATOR in roles
        assert PlatformRole.OWNER not in roles

    def test_has_platform_role(self):
        from core.permissions import PlatformRole, has_platform_role

        broadcaster = Mock()
        broadcaster.twitch_is_broadcaster = True
        broadcaster.twitch_is_moderator = False
        broadcaster.twitch_is_vip = False
        broadcaster.twitch_is_subscriber = False

        assert has_platform_role(broadcaster, PlatformRole.BROADCASTER, "twitch")
        assert has_platform_role(broadcaster, PlatformRole.MODERATOR, "twitch")
        assert has_platform_role(broadcaster, PlatformRole.VIP, "twitch")
        assert has_platform_role(broadcaster, PlatformRole.SUBSCRIBER, "twitch")
        assert has_platform_role(broadcaster, PlatformRole.VIEWER, "twitch")

        moderator = Mock()
        moderator.twitch_is_broadcaster = False
        moderator.twitch_is_moderator = True
        moderator.twitch_is_vip = False
        moderator.twitch_is_subscriber = False

        assert not has_platform_role(moderator, PlatformRole.BROADCASTER, "twitch")
        assert has_platform_role(moderator, PlatformRole.MODERATOR, "twitch")
        assert has_platform_role(moderator, PlatformRole.VIP, "twitch")
        assert has_platform_role(moderator, PlatformRole.SUBSCRIBER, "twitch")
        assert has_platform_role(moderator, PlatformRole.VIEWER, "twitch")

    def test_check_resource_ownership(self):
        from core.permissions import check_resource_ownership

        user = Mock()
        user.id = 123
        user.role = "user"
        assert check_resource_ownership(user, 123) is True
        assert check_resource_ownership(user, 456) is False

        admin = Mock()
        admin.id = 789
        admin.role = "admin"
        assert check_resource_ownership(admin, 123) is True
        assert check_resource_ownership(admin, 456) is True
        assert check_resource_ownership(admin, 789) is True

    def test_permission_decorators_exist(self):
        from core.permissions import require_ownership_or_admin, require_permission, require_platform_role, require_role

        assert callable(require_permission)
        assert callable(require_role)
        assert callable(require_platform_role)
        assert callable(require_ownership_or_admin)

    def test_role_hierarchy_completeness(self):
        from core.permissions import AppRole, ROLE_HIERARCHY

        for role in AppRole:
            assert role in ROLE_HIERARCHY, f"Role {role.value} not in hierarchy"

        admin_perms = len(ROLE_HIERARCHY[AppRole.ADMIN])
        user_perms = len(ROLE_HIERARCHY[AppRole.USER])
        assert admin_perms > user_perms

    def test_permission_system_files_exist(self):
        permissions_file = Path(__file__).resolve().parent.parent / "core/permissions.py"
        assert permissions_file.exists(), "permissions.py not found"

        with open(permissions_file, "r", encoding="utf-8") as file:
            content = file.read()

        assert "class AppRole" in content
        assert "class Permission" in content
        assert "class PlatformRole" in content
        assert "ROLE_HIERARCHY" in content
        assert "require_permission" in content


def run_tests():
    test_suite = TestPermissionSystem()
    tests = [
        test_suite.test_app_roles_defined,
        test_suite.test_permissions_defined,
        test_suite.test_platform_roles_defined,
        test_suite.test_admin_has_all_permissions,
        test_suite.test_user_has_correct_permissions,
        test_suite.test_platform_role_hierarchy,
        test_suite.test_get_platform_roles_twitch,
        test_suite.test_get_platform_roles_vk,
        test_suite.test_has_platform_role,
        test_suite.test_check_resource_ownership,
        test_suite.test_permission_decorators_exist,
        test_suite.test_role_hierarchy_completeness,
        test_suite.test_permission_system_files_exist,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception:
            failed += 1
            raise

    return failed == 0 and passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)

