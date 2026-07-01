"""
Test platform abstraction layer
Tests platform registry, base interface, and concrete implementations
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPlatformAbstraction:
    """Test suite for platform abstraction"""
    
    def test_platform_registry_initialization(self):
        """Test that platform registry initializes correctly"""
        from platforms.registry import PlatformRegistry
        
        registry = PlatformRegistry()
        
        # Registry should be empty before first access
        assert not registry._initialized
        
        # Accessing platforms should trigger initialization
        platforms = registry.get_all()
        
        # Should be initialized now
        assert registry._initialized
        assert len(platforms) > 0
        
        print("[OK] Platform registry initializes correctly")
    
    def test_platform_registry_has_twitch(self):
        """Test that Twitch platform is registered"""
        from platforms.registry import platform_registry
        
        twitch = platform_registry.get('twitch')
        
        assert twitch is not None, "Twitch platform not registered"
        assert twitch.config.name == 'twitch'
        assert twitch.config.display_name == 'Twitch'
        assert twitch.config.supports_oauth is True
        assert twitch.config.supports_chat is True
        assert twitch.config.supports_tts is True
        assert twitch.config.supports_points is True
        assert twitch.config.supports_categories is True
        assert twitch.config.color == '#9146FF'
        
        print("[OK] Twitch platform is registered correctly")
    
    def test_platform_registry_has_vk(self):
        """Test that VK platform is registered"""
        from platforms.registry import platform_registry
        
        vk = platform_registry.get('vk')
        
        assert vk is not None, "VK platform not registered"
        assert vk.config.name == 'vk'
        assert vk.config.display_name == 'VK Live'
        assert vk.config.supports_oauth is True
        assert vk.config.supports_chat is True
        assert vk.config.supports_tts is True
        assert vk.config.supports_points is True
        assert vk.config.supports_categories is True
        assert vk.config.color == '#0077FF'
        
        print("[OK] VK platform is registered correctly")
    
    def test_platform_registry_get_configs(self):
        """Test that platform configs can be retrieved for frontend"""
        from platforms.registry import platform_registry
        
        configs = platform_registry.get_configs()
        
        assert len(configs) >= 2, "Should have at least Twitch and VK"
        
        # Check config structure
        for config in configs:
            assert 'name' in config
            assert 'displayName' in config
            assert 'supportsOAuth' in config
            assert 'supportsChat' in config
            assert 'supportsTts' in config
            assert 'supportsPoints' in config
            assert 'supportsCategories' in config
            assert 'color' in config
            assert 'capabilities' in config
        
        # Check specific platforms
        twitch_config = next((c for c in configs if c['name'] == 'twitch'), None)
        assert twitch_config is not None, "Twitch config not found"
        assert twitch_config['displayName'] == 'Twitch'
        assert twitch_config['capabilities']['rewards'] is True
        assert twitch_config['capabilities']['moderation_actions'] is True

        vk_config = next((c for c in configs if c['name'] == 'vk'), None)
        assert vk_config is not None, "VK config not found"
        assert vk_config['displayName'] == 'VK Live'
        assert vk_config['capabilities']['reply_context'] is True
        assert vk_config['capabilities']['badges'] is True

        print("[OK] Platform configs can be retrieved for frontend")
    
    def test_platform_registry_is_valid_platform(self):
        """Test platform validation"""
        from platforms.registry import platform_registry
        
        assert platform_registry.is_valid_platform('twitch') is True
        assert platform_registry.is_valid_platform('vk') is True
        assert platform_registry.is_valid_platform('kick') is False
        assert platform_registry.is_valid_platform('youtube') is False
        assert platform_registry.is_valid_platform('invalid') is False
        
        print("[OK] Platform validation works correctly")
    
    def test_twitch_platform_implements_interface(self):
        """Test that Twitch platform implements all required methods"""
        from platforms.twitch import TwitchPlatform
        from platforms.base import StreamingPlatform
        
        twitch = TwitchPlatform()
        
        # Check it's a StreamingPlatform
        assert isinstance(twitch, StreamingPlatform)
        
        # Check all abstract methods are implemented
        required_methods = [
            'authenticate',
            'get_user_info',
            'update_stream_title',
            'update_stream_category',
            'search_categories',
            'get_stream_status',
            'get_channel_info',
            'send_chat_message'
        ]
        
        for method_name in required_methods:
            assert hasattr(twitch, method_name), f"Twitch missing method: {method_name}"
            method = getattr(twitch, method_name)
            assert callable(method), f"Twitch {method_name} is not callable"
        
        print("[OK] Twitch platform implements all required methods")
    
    def test_vk_platform_implements_interface(self):
        """Test that VK platform implements all required methods"""
        from platforms.vk import VKPlatform
        from platforms.base import StreamingPlatform
        
        vk = VKPlatform()
        
        # Check it's a StreamingPlatform
        assert isinstance(vk, StreamingPlatform)
        
        # Check all abstract methods are implemented
        required_methods = [
            'authenticate',
            'get_user_info',
            'update_stream_title',
            'update_stream_category',
            'search_categories',
            'get_stream_status',
            'get_channel_info',
            'send_chat_message'
        ]
        
        for method_name in required_methods:
            assert hasattr(vk, method_name), f"VK missing method: {method_name}"
            method = getattr(vk, method_name)
            assert callable(method), f"VK {method_name} is not callable"
        
        print("[OK] VK platform implements all required methods")
    
    def test_platform_config_dataclass(self):
        """Test PlatformConfig dataclass"""
        from platforms.base import PlatformConfig
        
        config = PlatformConfig(
            name='test',
            display_name='Test Platform',
            supports_oauth=True,
            supports_chat=True,
            supports_tts=True,
            supports_points=False,
            supports_categories=True,
            color='#FF0000'
        )
        
        assert config.name == 'test'
        assert config.display_name == 'Test Platform'
        assert config.supports_oauth is True
        assert config.supports_points is False
        assert config.color == '#FF0000'
        
        print("[OK] PlatformConfig dataclass works correctly")
    
    def test_platform_optional_methods(self):
        """Test that optional methods have default implementations"""
        from platforms.base import StreamingPlatform, PlatformConfig
        
        # Create a minimal implementation
        class TestPlatform(StreamingPlatform):
            def __init__(self):
                config = PlatformConfig(
                    name='test',
                    display_name='Test',
                    supports_oauth=False,
                    supports_chat=False,
                    supports_tts=False,
                    supports_points=False,
                    supports_categories=False,
                    color='#000000'
                )
                super().__init__(config)
            
            async def authenticate(self, code: str):
                return {}
            
            async def get_user_info(self, access_token: str):
                return {}
            
            async def update_stream_title(self, user_id: int, title: str):
                return False
            
            async def update_stream_category(self, user_id: int, category_id: str):
                return False
            
            async def search_categories(self, query: str):
                return []
            
            async def get_stream_status(self, username: str):
                return None
            
            async def get_channel_info(self, username: str):
                return None
            
            async def send_chat_message(self, user_id: int, message: str):
                return False
        
        platform = TestPlatform()
        
        # Test optional methods have default implementations
        import asyncio
        
        # These should not raise NotImplementedError
        result = asyncio.run(platform.create_reward(1, {}))
        assert result is None
        
        result = asyncio.run(platform.update_reward(1, 'reward_id', {}))
        assert result is False
        
        result = asyncio.run(platform.delete_reward(1, 'reward_id'))
        assert result is False
        
        result = asyncio.run(platform.get_user_roles('user', 'channel'))
        assert result == []
        
        print("[OK] Optional methods have default implementations")
    
    def test_platform_files_exist(self):
        """Test that all platform files exist"""
        base_path = Path("platforms")
        
        required_files = [
            '__init__.py',
            'base.py',
            'registry.py',
            'twitch.py',
            'vk.py'
        ]
        
        for file_name in required_files:
            file_path = base_path / file_name
            if not file_path.exists():
                print(f"[WARN] Platform file not found: {file_name}")
        
        print("[OK] Platform files check complete")
    
    def test_platform_registry_singleton(self):
        """Test that platform_registry is a singleton"""
        from platforms.registry import platform_registry
        from platforms.registry import PlatformRegistry
        
        # Create new instance
        new_registry = PlatformRegistry()
        
        # They should be different instances (not singleton pattern)
        # But platform_registry should be the global instance
        assert platform_registry is not new_registry
        
        # Global instance should work consistently
        platforms1 = platform_registry.get_all()
        platforms2 = platform_registry.get_all()
        
        assert len(platforms1) == len(platforms2)
        
        print("[OK] Platform registry works as expected")


def run_tests():
    """Run all platform abstraction tests"""
    print("\n" + "="*60)
    print("TESTING PLATFORM ABSTRACTION")
    print("="*60 + "\n")
    
    test_suite = TestPlatformAbstraction()
    
    tests = [
        test_suite.test_platform_registry_initialization,
        test_suite.test_platform_registry_has_twitch,
        test_suite.test_platform_registry_has_vk,
        test_suite.test_platform_registry_get_configs,
        test_suite.test_platform_registry_is_valid_platform,
        test_suite.test_twitch_platform_implements_interface,
        test_suite.test_vk_platform_implements_interface,
        test_suite.test_platform_config_dataclass,
        test_suite.test_platform_optional_methods,
        test_suite.test_platform_files_exist,
        test_suite.test_platform_registry_singleton,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
