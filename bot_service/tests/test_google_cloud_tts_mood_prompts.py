from services.tts.google_cloud_tts import get_gcloud_prompt_for_mood, normalize_gcloud_mood


def test_normalize_gcloud_mood_defaults_to_neutral():
    assert normalize_gcloud_mood(None) == "neutral"
    assert normalize_gcloud_mood("unknown") == "neutral"


def test_gcloud_mood_prompts_use_safe_style_instructions():
    prompts = {
        mood: get_gcloud_prompt_for_mood(mood)
        for mood in ("neutral", "sad", "happy")
    }

    assert prompts["neutral"] == "Speak naturally, clearly, and conversationally."
    assert prompts["sad"] == "Speak softly with a calm, subdued tone."
    assert prompts["happy"] == "Speak warmly with a cheerful, upbeat tone."

    forbidden_fragments = (
        "mostly you are happy",
        "no one knows what to expect from you",
        "depressive",
    )
    for prompt in prompts.values():
        prompt_lower = prompt.lower()
        for fragment in forbidden_fragments:
            assert fragment not in prompt_lower
