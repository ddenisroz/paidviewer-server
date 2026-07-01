"""
Тесты для YouTube URL валидаторов
"""
import pytest
from validators.youtube_validators import (
    validate_youtube_url,
    is_valid_youtube_url,
    extract_video_id
)


class TestYouTubeValidators:
    """Тесты для валидации YouTube URL"""
    
    def test_valid_youtube_com_watch_url(self):
        """Тест валидного youtube.com/watch?v= URL"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_valid_youtu_be_url(self):
        """Тест валидного youtu.be/ URL"""
        url = "https://youtu.be/dQw4w9WgXcQ"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_valid_youtube_embed_url(self):
        """Тест валидного youtube.com/embed/ URL"""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_valid_youtube_v_url(self):
        """Тест валидного youtube.com/v/ URL"""
        url = "https://www.youtube.com/v/dQw4w9WgXcQ"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_youtube_url_with_parameters(self):
        """Тест YouTube URL с дополнительными параметрами"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLtest"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_youtube_url_without_protocol(self):
        """Тест YouTube URL без протокола"""
        url = "youtube.com/watch?v=dQw4w9WgXcQ"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_youtube_url_without_www(self):
        """Тест YouTube URL без www"""
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXcQ"
        assert error == ""
    
    def test_invalid_not_youtube_url(self):
        """Тест невалидного URL (не YouTube)"""
        url = "https://vimeo.com/123456789"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert "Not a YouTube URL" in error
    
    def test_invalid_youtube_url_no_video_id(self):
        """Тест YouTube URL без video_id"""
        url = "https://www.youtube.com"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert error != ""
    
    def test_invalid_youtube_url_short_video_id(self):
        """Тест YouTube URL с коротким video_id"""
        url = "https://www.youtube.com/watch?v=short"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert error != ""
    
    def test_invalid_empty_url(self):
        """Тест пустого URL"""
        url = ""
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert "empty" in error.lower()
    
    def test_invalid_none_url(self):
        """Тест None URL"""
        url = None
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert error != ""
    
    def test_invalid_too_long_url(self):
        """Тест слишком длинного URL"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" + "a" * 500
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert "too long" in error.lower()
    
    def test_invalid_malicious_url(self):
        """Тест потенциально вредоносного URL"""
        url = "javascript:alert('XSS')"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is False
        assert video_id == ""
        assert error != ""
    
    def test_is_valid_youtube_url_helper(self):
        """Тест вспомогательной функции is_valid_youtube_url"""
        assert is_valid_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
        assert is_valid_youtube_url("https://vimeo.com/123") is False
        assert is_valid_youtube_url("") is False
    
    def test_extract_video_id_helper(self):
        """Тест вспомогательной функции extract_video_id"""
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert extract_video_id("https://vimeo.com/123") == ""
        assert extract_video_id("") == ""
    
    def test_video_id_with_special_characters(self):
        """Тест video_id со специальными символами (дефис и подчеркивание)"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXc-"
        is_valid, video_id, error = validate_youtube_url(url)
        
        assert is_valid is True
        assert video_id == "dQw4w9WgXc-"
        assert error == ""
        
        url2 = "https://www.youtube.com/watch?v=dQw4w9WgXc_"
        is_valid2, video_id2, error2 = validate_youtube_url(url2)
        
        assert is_valid2 is True
        assert video_id2 == "dQw4w9WgXc_"
        assert error2 == ""
