from services.tts.language_routing import detect_language_routing, enrich_tts_settings_with_language_routing


def test_detect_language_routing_keeps_urls_mentions_and_emotes_out_of_latin_trigger():
    result = detect_language_routing("Привет https://example.com @user :KEKW:")

    assert result["route_target"] == "ru_misha"
    assert result["requires_bilingual_checkpoint"] is False
    assert result["plain_latin_words_preview"] == []


def test_detect_language_routing_marks_mixed_text_for_bilingual_checkpoint():
    result = detect_language_routing("Привет chat today мы смотрим trailer")

    assert result["route_target"] == "mixed_en_bilingual"
    assert result["detected_language"] == "mixed"
    assert result["requires_bilingual_checkpoint"] is True
    assert "chat" in [word.lower() for word in result["plain_latin_words_preview"]]


def test_enrich_tts_settings_with_language_routing_preserves_existing_fields():
    settings = enrich_tts_settings_with_language_routing({"voice": "Female_1"}, "hello world")

    assert settings["voice"] == "Female_1"
    assert settings["language_routing"]["route_target"] == "en_bilingual"
