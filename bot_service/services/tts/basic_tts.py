#!/usr/bin/env python3
"""
Basic Google Text-to-Speech (gTTS) fallback service.

Used by bot_service when the main F5-TTS service is unavailable.
Does not require a GPU and works through the Google TTS API.
"""
import logging
import re
from pathlib import Path
from typing import Optional
import time
from gtts import gTTS
from pydub import AudioSegment
logger = logging.getLogger(__name__)

class BasicTTS:
    """
    Basic gTTS-based fallback TTS engine for bot_service.

    Benefits:
    - no GPU or heavy runtime required
    - uses the Google TTS API
    - supports Russian and English
    - available to every user without a whitelist
    - fast to generate
    - independent from the external TTS runtime
    """

    def __init__(self, temp_dir: Optional[Path]=None):
        """
        Initialize the basic TTS service.

        Args:
            temp_dir: Directory for temporary files. Defaults to the project temp directory.
        """
        if temp_dir:
            self.temp_dir = Path(temp_dir)
        else:
            from core.project_paths import TEMP_DIR
            self.temp_dir = TEMP_DIR / 'tts_audio'
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f'[OK] Basic TTS (gTTS) initialized. Temp dir: {self.temp_dir}')

    def is_ready(self) -> bool:
        """Check TTS readiness. Always returns True for gTTS."""
        return True

    def detect_language(self, text: str) -> str:
        """
        Detect the text language.

        Returns:
            'ru' for Russian and 'en' for English.
        """
        cyrillic_pattern = re.compile('[\\u0430-\\u044f\\u0451]', re.IGNORECASE)
        latin_pattern = re.compile('[a-z]', re.IGNORECASE)
        cyrillic_count = len(cyrillic_pattern.findall(text))
        latin_count = len(latin_pattern.findall(text))
        if cyrillic_count > latin_count:
            return 'ru'
        elif latin_count > cyrillic_count:
            return 'en'
        elif cyrillic_count > 0:
            return 'ru'
        else:
            return 'ru'

    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text before synthesis.

        Applies basic cleanup without depending on advanced text-normalization modules.
        """
        processed_text = re.sub('\\s+', ' ', text.strip())
        if not processed_text:
            return ''
        url_pattern = '(https?://|www\\.|[a-zA-Z0-9-]+\\.(com|ru|net|org|tv|gg|me|io|co|us|uk|de|fr|cn|jp|br|in|au|ca|eu))'
        if re.search(url_pattern, processed_text, re.IGNORECASE):
            logger.warning(f'[BLOCKED] Text contains a URL and will be skipped: {processed_text[:50]}...')
            return ''
        text_no_spaces = processed_text.replace(' ', '')
        has_letter_or_digit = any((c.isalnum() for c in text_no_spaces))
        if not has_letter_or_digit:
            logger.warning('Text contains only symbols and will be ignored')
            return ''
        processed_text = re.sub('(.)\\1{3,}', '\\1\\1\\1', processed_text)
        if not processed_text.strip():
            logger.warning('Text became empty after repeated-sequence cleanup')
            return ''
        if not processed_text.endswith(('.', '!', '?', '...')):
            processed_text += '.'
        processed_text = re.sub('\\s+', ' ', processed_text).strip()
        return processed_text

    def synthesize_speech(self, text: str, volume_level: float=50.0, speed: float=1.0, voice: str='com', **kwargs) -> Optional[str]:
        """
        Synthesize speech with gTTS.

        Args:
            text: Input text to synthesize.
            volume_level: Volume level in the 0-100 range.
            speed: Playback speed in the 0.5-2.0 range. Defaults to 1.0.
            voice: Accent/voice variant via the gTTS `tld` parameter.
            **kwargs: Extra compatibility arguments ignored by this implementation.

        Returns:
            Absolute path to the generated audio file, or None on failure.
        """
        try:
            processed_text = self.preprocess_text(text)
            if not processed_text:
                logger.warning('Text is empty after preprocessing')
                return None
            language = self.detect_language(processed_text)
            logger.info(f"[LANG] Basic TTS: language={language}, text='{processed_text[:50]}...'")
            timestamp = int(time.time() * 1000)
            temp_mp3 = self.temp_dir / f'basic_tts_{timestamp}.mp3'
            output_wav = self.temp_dir / f'basic_tts_{timestamp}.wav'
            slow_mode = speed < 0.8
            tld = voice if voice else 'com'
            tts = gTTS(text=processed_text, lang=language, slow=slow_mode, tld=tld)
            tts.save(str(temp_mp3))
            logger.info(f'[MIC] gTTS: language={language}, accent={tld}, slow={slow_mode}')
            logger.info(f'[OK] gTTS audio generated: {temp_mp3}')
            audio = AudioSegment.from_mp3(str(temp_mp3))
            if not slow_mode and speed != 1.0:
                speed_factor = speed
                audio = audio.speedup(playback_speed=speed_factor)
                logger.info(f'[SPEED] Applied playback speed: {speed}x')
            if volume_level != 50.0:
                db_change = (volume_level - 50) / 50 * 10
                audio = audio + db_change
                logger.info(f'[VOLUME] Applied volume level: {volume_level}% ({db_change:+.1f}dB)')
            silence = AudioSegment.silent(duration=300)
            audio = audio + silence
            audio.export(str(output_wav), format='wav', parameters=['-ar', '24000', '-ac', '1'])
            logger.info(f'[DB] Basic TTS saved to WAV: {output_wav}')
            try:
                temp_mp3.unlink()
            except Exception:
                logger.exception('Failed to delete temporary MP3 file')
            return str(output_wav.resolve())
        except Exception:
            logger.exception('[ERROR] Failed to generate audio via gTTS')
            return None

    def cleanup_old_files(self, max_age_seconds: int=3600):
        """
        Remove old temporary files.

        Args:
            max_age_seconds: Maximum file age in seconds. Defaults to one hour.
        """
        try:
            current_time = time.time()
            deleted_count = 0
            for file_path in self.temp_dir.glob('basic_tts_*'):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        deleted_count += 1
            if deleted_count > 0:
                logger.info(f'[DELETE] Removed {deleted_count} old basic TTS files')
        except Exception:
            logger.exception('[ERROR] Failed to clean temporary files')
_basic_tts_instance = None

def get_basic_tts() -> BasicTTS:
    """Return the shared BasicTTS singleton."""
    global _basic_tts_instance
    if _basic_tts_instance is None:
        _basic_tts_instance = BasicTTS()
    return _basic_tts_instance
