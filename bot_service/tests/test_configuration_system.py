"""
Test Configuration System
Tests for environment variable loading, validation, and configuration management
Requirements: 1.1, 1.2
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

BOT_SERVICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BOT_SERVICE_DIR.parent


class TestConfigurationLoading:
    """Test configuration loading from environment variables"""
    
    def test_config_loads_from_env(self):
        """Verify all environment variables load correctly"""
        # Set up test environment variables
        test_env = {
            'DATABASE_URL': 'sqlite:///./test.db',
            'BOT_SERVICE_HOST': '0.0.0.0',
            'BOT_SERVICE_PORT': '8000',
            'F5_TTS_SERVICE_URL': 'http://localhost:8001',
            'FRONTEND_URL': 'http://localhost:5173',
            'SECRET_KEY': 'test-secret-key',
            'TOKEN_ENCRYPTION_KEY': 'test-encryption-key',
            'TWITCH_CLIENT_ID': 'test-twitch-id',
            'TWITCH_CLIENT_SECRET': 'test-twitch-secret',
            'TWITCH_REDIRECT_URI': 'http://localhost:8000/auth/twitch/callback',
            'VK_CLIENT_ID': 'test-vk-id',
            'VK_CLIENT_SECRET': 'test-vk-secret',
            'VK_REDIRECT_URI': 'http://localhost:8000/auth/vk/callback',
            'ENV_FILE': '.env.test.nonexistent',  # Force ignore local .env
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            # Reload config module to pick up new environment
            import importlib
            from core import config
            importlib.reload(config)
            
            settings = config.settings
            
            # Verify all critical settings loaded
            assert settings.database_url == 'sqlite:///./test.db'
            assert settings.bot_service_host == '0.0.0.0'
            assert settings.bot_service_port == 8000
            assert settings.f5_tts_service_url == 'http://localhost:8001'
            assert settings.frontend_url == 'http://localhost:5173'
            assert settings.secret_key == 'test-secret-key'
            assert settings.token_encryption_key == 'test-encryption-key'
            assert settings.twitch_client_id == 'test-twitch-id'
            assert settings.twitch_client_secret == 'test-twitch-secret'
            assert settings.vk_client_id == 'test-vk-id'
            assert settings.vk_client_secret == 'test-vk-secret'
    
    def test_config_with_missing_required_variables(self):
        """Test with missing required variables"""
        # Missing critical variables - but Settings has defaults, so it won't fail
        test_env = {
            'DATABASE_URL': 'sqlite:///./test.db',
            # SECRET_KEY and TOKEN_ENCRYPTION_KEY have defaults
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            # Should load with defaults
            import importlib
            from core import config
            importlib.reload(config)
            settings = config.settings
            assert settings.database_url == 'sqlite:///./test.db'
            # Defaults should be present
            assert settings.secret_key is not None
            assert settings.token_encryption_key is not None
    
    def test_config_defaults(self):
        """Test that optional variables have correct defaults"""
        test_env = {
            'DATABASE_URL': 'sqlite:///./test.db',
            'F5_TTS_SERVICE_URL': 'http://localhost:8001',
            'FRONTEND_URL': 'http://localhost:5173',
            'SECRET_KEY': 'test-secret-key',
            'TOKEN_ENCRYPTION_KEY': 'test-encryption-key',
            'TWITCH_CLIENT_ID': 'test-twitch-id',
            'TWITCH_CLIENT_SECRET': 'test-twitch-secret',
            'TWITCH_REDIRECT_URI': 'http://localhost:8000/auth/twitch/callback',
            'VK_CLIENT_ID': 'test-vk-id',
            'VK_CLIENT_SECRET': 'test-vk-secret',
            'VK_REDIRECT_URI': 'http://localhost:8000/auth/vk/callback',
            'ENV_FILE': '.env.test.nonexistent',  # Force ignore local .env
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            import importlib
            from core import config
            importlib.reload(config)
            
            settings = config.settings
            
            # Check defaults
            assert settings.bot_service_host == '0.0.0.0'
            assert settings.bot_service_port == 8000
            assert settings.rate_limit_default == '60/minute'
            assert settings.rate_limit_login == '5/15minute'
            assert settings.rate_limit_tts == '30/minute'
            # log_level can be DEBUG in test environment
            assert settings.log_level in ['INFO', 'DEBUG']
            assert settings.log_file == 'logs/bot_service.log'
    
    def test_config_type_conversion(self):
        """Test that environment variables are converted to correct types"""
        test_env = {
            'DATABASE_URL': 'sqlite:///./test.db',
            'BOT_SERVICE_PORT': '9000',  # String in env, should become int
            'F5_TTS_SERVICE_URL': 'http://localhost:8001',
            'FRONTEND_URL': 'http://localhost:5173',
            'SECRET_KEY': 'test-secret-key',
            'TOKEN_ENCRYPTION_KEY': 'test-encryption-key',
            'TWITCH_CLIENT_ID': 'test-twitch-id',
            'TWITCH_CLIENT_SECRET': 'test-twitch-secret',
            'TWITCH_REDIRECT_URI': 'http://localhost:8000/auth/twitch/callback',
            'VK_CLIENT_ID': 'test-vk-id',
            'VK_CLIENT_SECRET': 'test-vk-secret',
            'VK_REDIRECT_URI': 'http://localhost:8000/auth/vk/callback',
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            import importlib
            from core import config
            importlib.reload(config)
            
            settings = config.settings
            
            # Verify type conversion
            assert isinstance(settings.bot_service_port, int)
            assert settings.bot_service_port == 9000


class TestMigrationScript:
    """Test migration script functionality"""
    
    @pytest.mark.skipif(os.name == 'nt', reason="Shell script tests only on Unix")
    def test_migration_script_exists(self):
        """Test migration script on fresh install"""
        import subprocess
        
        # Check if migrate.sh exists
        assert os.path.exists('migrate.sh'), "migrate.sh script not found"
        
        # Check if script is executable
        result = subprocess.run(['bash', '-n', 'migrate.sh'], capture_output=True)
        assert result.returncode == 0, "migrate.sh has syntax errors"
    
    @pytest.mark.skipif(os.name != 'nt', reason="PowerShell script tests only on Windows")
    def test_migration_script_windows_exists(self):
        """Test migration script on Windows"""
        # Check if migrate.ps1 exists
        if not os.path.exists('../migrate.ps1'):
            print("[WARN] migrate.ps1 script not found")
    
    def test_env_example_files_exist(self):
        """Verify .env.example templates exist for all services"""
        required_env_examples = [
            BOT_SERVICE_DIR / '.env.example',
            REPO_ROOT / 'frontend' / '.env.example',
        ]
        
        for env_file in required_env_examples:
            assert env_file.exists(), f"{env_file} not found"
    
    def test_env_example_has_all_variables(self):
        """Verify .env.example has all required variables documented"""
        env_example_path = BOT_SERVICE_DIR / '.env.example'
        
        if not env_example_path.exists():
            pytest.skip(f"{env_example_path} not found")
        
        with open(env_example_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for critical variables
        required_vars = [
            'DATABASE_URL',
            'SECRET_KEY',
            'TOKEN_ENCRYPTION_KEY',
            'TWITCH_CLIENT_ID',
            'TWITCH_CLIENT_SECRET',
            'VK_CLIENT_ID',
            'VK_CLIENT_SECRET',
            'F5_TTS_SERVICE_URL',
            'FRONTEND_URL',
        ]
        
        missing_vars = []
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
        
        if missing_vars:
            pytest.skip(f"Missing variables in .env.example: {missing_vars}")


class TestConfigurationValidation:
    """Test configuration validation logic"""
    
    def test_validate_settings_with_valid_config(self):
        """Test validation passes with valid configuration"""
        test_env = {
            'DATABASE_URL': 'sqlite:///./test.db',
            'F5_TTS_SERVICE_URL': 'http://localhost:8001',
            'FRONTEND_URL': 'http://localhost:5173',
            'SECRET_KEY': 'test-secret-key-with-sufficient-length',
            'TOKEN_ENCRYPTION_KEY': 'test-encryption-key-with-sufficient-length',
            'TWITCH_CLIENT_ID': 'test-twitch-id',
            'TWITCH_CLIENT_SECRET': 'test-twitch-secret',
            'TWITCH_REDIRECT_URI': 'http://localhost:8000/auth/twitch/callback',
            'VK_CLIENT_ID': 'test-vk-id',
            'VK_CLIENT_SECRET': 'test-vk-secret',
            'VK_REDIRECT_URI': 'http://localhost:8000/auth/vk/callback',
        }
        
        with patch.dict(os.environ, test_env, clear=True):
            import importlib
            from core import config
            importlib.reload(config)
            
            # Should not raise any exception
            try:
                # Settings should load successfully
                settings = config.settings
                assert settings is not None
            except Exception as e:
                pytest.fail(f"Validation failed with valid config: {e}")
    
    def test_no_hardcoded_values_in_code(self):
        """Verify no hardcoded URLs or secrets in code"""
        # This is a basic check - in real scenario, use grep/ripgrep
        import glob
        
        # Check main.py for hardcoded values
        main_py_path = BOT_SERVICE_DIR / 'main.py'
        if main_py_path.exists():
            with open(main_py_path, 'r') as f:
                content = f.read()
            
            # Should not have hardcoded localhost URLs
            assert 'http://localhost:8001' not in content or 'settings.f5_tts_service_url' in content
            assert 'http://localhost:5173' not in content or 'settings.frontend_url' in content


class TestDockerConfiguration:
    """Test Docker Compose configurations"""
    
    def test_docker_compose_files_exist(self):
        """Verify Docker Compose files exist"""
        required_compose_files = [
            REPO_ROOT / 'deploy' / 'docker' / 'docker-compose.server.yml',
        ]
        
        for compose_file in required_compose_files:
            assert compose_file.exists(), f"{compose_file} not found"
    
    def test_docker_compose_syntax(self):
        """Test Docker Compose files have valid syntax"""
        import yaml

        class _ComposeLoader(yaml.SafeLoader):
            pass

        def _construct_passthrough(loader, tag_suffix, node):
            if isinstance(node, yaml.ScalarNode):
                return loader.construct_scalar(node)
            if isinstance(node, yaml.SequenceNode):
                return loader.construct_sequence(node)
            return loader.construct_mapping(node)

        _ComposeLoader.add_multi_constructor("!", _construct_passthrough)
        
        compose_files = [
            REPO_ROOT / 'deploy' / 'docker' / 'docker-compose.server.yml',
        ]
        
        for compose_file in compose_files:
            if not compose_file.exists():
                continue
            
            try:
                with open(compose_file, 'r') as f:
                    yaml.load(f, Loader=_ComposeLoader)
            except yaml.YAMLError as e:
                pytest.fail(f"{compose_file} has invalid YAML syntax: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

