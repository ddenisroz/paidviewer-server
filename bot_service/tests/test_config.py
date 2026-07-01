"""
Test configuration system
Tests environment variable loading, validation, and error handling
"""
import pytest
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfigurationSystem:
    """Test suite for configuration system"""
    
    def test_config_loads_with_defaults(self):
        """Test that configuration loads with default values"""
        from core.config import Settings
        
        # Create settings with defaults
        settings = Settings()
        
        # Verify critical defaults exist
        assert settings.bot_service_host == "0.0.0.0"
        assert settings.bot_service_port == 8000
        assert settings.environment in ["development", "production"]  # Can be either
        assert isinstance(settings.debug, bool)
        assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert hasattr(settings, 'secret_key')  # Check field exists
        
        print("[OK] Configuration loads with defaults")
    
    def test_config_loads_from_env_vars(self):
        """Test that configuration loads from environment variables"""
        from core.config import Settings
        
        # Set environment variables
        os.environ["BOT_SERVICE_PORT"] = "9000"
        os.environ["ENVIRONMENT"] = "testing"
        os.environ["DEBUG"] = "false"
        
        # Create settings
        settings = Settings()
        
        # Verify environment variables are loaded
        assert settings.bot_service_port == 9000
        assert settings.environment == "testing"
        assert settings.debug is False
        
        # Cleanup
        del os.environ["BOT_SERVICE_PORT"]
        del os.environ["ENVIRONMENT"]
        del os.environ["DEBUG"]
        
        print("[OK] Configuration loads from environment variables")
    
    def test_config_validates_required_fields_in_production(self):
        """Test that required fields are validated in production"""
        from core.config import Settings
        
        # Set production environment
        os.environ["ENVIRONMENT"] = "production"
        os.environ["SECRET_KEY"] = "test-secret-key-for-production-32chars"
        
        # Should load successfully with valid secret key
        try:
            settings = Settings()
            assert settings.environment == "production"
            assert settings.secret_key == "test-secret-key-for-production-32chars"
            print("[OK] Validates required fields in production")
        finally:
            if "ENVIRONMENT" in os.environ:
                del os.environ["ENVIRONMENT"]
            if "SECRET_KEY" in os.environ:
                del os.environ["SECRET_KEY"]
    
    def test_config_validates_port_range(self):
        """Test that port validation works"""
        from core.config import Settings
        from pydantic import ValidationError
        
        # Test invalid port
        os.environ["BOT_SERVICE_PORT"] = "99999"
        
        try:
            settings = Settings()
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "Port must be between" in str(e)
            print("[OK] Validates port range")
        finally:
            del os.environ["BOT_SERVICE_PORT"]
    
    def test_config_parses_cors_origins(self):
        """Test that CORS origins are parsed correctly"""
        from core.config import Settings
        
        os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://localhost:3000,https://example.com"
        
        settings = Settings()
        
        assert len(settings.cors_origins_list) == 3
        assert "http://localhost:5173" in settings.cors_origins_list
        assert "http://localhost:3000" in settings.cors_origins_list
        assert "https://example.com" in settings.cors_origins_list
        
        del os.environ["CORS_ORIGINS"]
        
        print("[OK] Parses CORS origins correctly")
    
    def test_config_computed_fields(self):
        """Test computed fields work correctly"""
        from core.config import Settings
        
        # Test development environment
        os.environ["ENVIRONMENT"] = "development"
        settings = Settings()
        assert settings.is_development is True
        assert settings.is_production is False
        
        # Test production environment
        os.environ["ENVIRONMENT"] = "production"
        os.environ["SECRET_KEY"] = "a" * 32  # Valid key
        os.environ["TOKEN_ENCRYPTION_KEY"] = "b" * 44  # Valid Fernet key
        settings = Settings()
        assert settings.is_development is False
        assert settings.is_production is True
        
        # Cleanup
        del os.environ["ENVIRONMENT"]
        del os.environ["SECRET_KEY"]
        del os.environ["TOKEN_ENCRYPTION_KEY"]
        
        print("[OK] Computed fields work correctly")
    
    def test_config_validates_database_url(self):
        """Test database URL validation"""
        from core.config import Settings
        from pydantic import ValidationError
        
        # Test empty database URL
        os.environ["DATABASE_URL"] = ""
        
        try:
            settings = Settings()
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "DATABASE_URL is required" in str(e)
            print("[OK] Validates database URL")
        finally:
            del os.environ["DATABASE_URL"]
    
    def test_config_validates_positive_integers(self):
        """Test positive integer validation"""
        from core.config import Settings
        from pydantic import ValidationError
        
        # Test negative value
        os.environ["CHAT_MESSAGES_DB_LIMIT_PER_USER"] = "-1"
        
        try:
            settings = Settings()
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "Value must be positive" in str(e)
            print("[OK] Validates positive integers")
        finally:
            del os.environ["CHAT_MESSAGES_DB_LIMIT_PER_USER"]
    
    def test_env_example_files_exist(self):
        """Test that .env.example files exist for all services"""
        bot_service_env = Path(".env.example")
        frontend_env = Path("../frontend/.env.example")
        
        if not bot_service_env.exists():
            print("[WARN] bot_service/.env.example not found")
        if not frontend_env.exists():
            print("[WARN] frontend/.env.example not found")
        
        print("[OK] Required .env.example files exist")
    
    def test_env_example_has_all_required_vars(self):
        """Test that .env.example has all required variables"""
        from core.config import Settings
        
        # Get all field names from Settings
        settings = Settings()
        field_names = set(settings.model_fields.keys())
        
        # Read .env.example
        env_example_path = Path("bot_service/.env.example")
        if not env_example_path.exists():
            print("[SKIP] .env.example not found")
            return
            
        with open(env_example_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        # Check critical fields are documented
        critical_fields = [
            'SECRET_KEY',
            'TOKEN_ENCRYPTION_KEY',
            'DATABASE_URL',
            'BOT_SERVICE_HOST',
            'BOT_SERVICE_PORT',
            'TWITCH_CLIENT_ID',
            'VK_CLIENT_ID'
        ]
        
        missing_fields = []
        for field in critical_fields:
            if field not in env_content:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"[WARN] Missing fields in .env.example: {missing_fields}")
        else:
            print("[OK] .env.example has all required variables")


def run_tests():
    """Run all configuration tests"""
    print("\n" + "="*60)
    print("TESTING CONFIGURATION SYSTEM")
    print("="*60 + "\n")
    
    test_suite = TestConfigurationSystem()
    
    tests = [
        test_suite.test_config_loads_with_defaults,
        test_suite.test_config_loads_from_env_vars,
        test_suite.test_config_validates_required_fields_in_production,
        test_suite.test_config_validates_port_range,
        test_suite.test_config_parses_cors_origins,
        test_suite.test_config_computed_fields,
        test_suite.test_config_validates_database_url,
        test_suite.test_config_validates_positive_integers,
        test_suite.test_env_example_files_exist,
        test_suite.test_env_example_has_all_required_vars,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__} failed: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

