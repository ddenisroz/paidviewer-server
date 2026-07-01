# Technical Debt

This file tracks only confirmed or strongly evidenced technical debt.
It is not a wishlist. Each item below is either:
- visible in current runtime logs,
- confirmed by user-facing broken behavior,
- or left partially implemented during the ongoing repair work.

## P0 - Reliability blockers

### 1. Live TTS flow is not yet proven equivalent to preview flow
- Status: open
- Why this is debt:
  - Preview/test audio working does not guarantee that real incoming chat messages use the same provider, voice, volume, and sink path.
- Remaining debt:
  - Verify end-to-end live message flow for F5 cloud and F5 self-host.
  - Confirm that saved settings are applied immediately in normal runtime, not only in preview requests.

### 2. F5 runtime still carries fragile import surface
- Status: partially fixed
- Evidence:
  - Earlier runtime failures included missing `torchcodec`.
  - Current F5 logs still show warning-level fallback around optional imports such as `wandb`.
- Remaining debt:
  - Reduce runtime-only dependency ambiguity in the container image.
  - Recheck that health/readiness and admin preview remain honest after a clean rebuild.

## P1 - Core product behavior

### 3. MemeAlerts auth flow still needs full browser-level acceptance verification
- Status: partially repaired
- What changed:
  - Callback/token persistence flow was hardened.
  - Browser auth entrypoint now starts from provider-aware popup routes and goes straight into `/api/auth/{provider}` instead of the broken proxied landing modal.
  - Proxy fallback remains only for token capture / callback safety when upstream rejects the direct callback URL.
- Remaining debt:
  - Confirm end-to-end behavior in real browser interaction:
    - popup opens,
    - callback returns,
    - token is stored,
    - status updates without manual refresh.
  - Verify all three providers (`Twitch`, `Google`, `VK`) survive real upstream auth changes without needing manual token paste.

### 4. Voice management needs full end-to-end provider validation
- Status: open
- Notes:
  - Runtime behavior for "no user voices yet" is handled, but the full UX still needs a full pass.
- Remaining debt:
  - Re-verify for F5:
    - upload
    - list
    - rename
    - delete
    - retranscribe
    - enable/disable
    - preview/test
  - Ensure stale UI state is invalidated consistently after mutations.

### 5. TTS settings responsiveness still needs a focused UX pass
- Status: open
- Why this is debt:
  - The user still reports that sliders/settings do not feel reliably applied.
- Remaining debt:
  - Verify which settings are preview-only versus live-runtime affecting.
  - Ensure save responses are reflected immediately in UI state.
  - Remove any hidden fallback path where old values can still be used after a save.
  - Reconfirm slider and mode changes through live message synthesis, not only preview.

## P1 - Functional gaps outside TTS

### 6. Commands feature is not fully repaired
- Status: partially repaired
- What changed:
  - Global catalog for `title` / `game` remains seeded on startup.
  - Commands editor now treats user overrides for global commands as override flows instead of pretending they are custom renames.
  - Touched command forms and validation messages were cleaned from broken encoding.
- Remaining debt:
  - Finish support for `title` / `game` command flows.
  - Recheck rename behavior for custom commands.
  - Recheck alias override behavior for global commands.
  - Recheck uniqueness validation per user/platform.

### 7. Rewards integration needs a full scenario pass
- Status: partially repaired
- What changed:
  - Some Twitch/VK capability messaging was normalized.
- Remaining debt:
  - Verify create/update/toggle/delete flows for:
    - TTS rewards
    - MemeAlerts rewards
    - YouTube request rewards
    - dedicated rewards tab
  - Reconfirm platform-specific error messaging in real UI behavior.

### 8. Drops logic is still too complex relative to the intended product rule set
- Status: open
- Why this is debt:
  - Current logic does not yet match the simpler product model requested by the user.
- Remaining debt:
  - Reduce canonical rules to:
    - message-based streak progression,
    - donation-amount rarity mapping,
    - channel-points chest purchase.
  - Remove or demote legacy branches that complicate maintenance without adding product value.

### 10. Drops OBS widget redesign is still not implemented
- Status: open
- Remaining debt:
  - Add the intended chest appearance + case-opening style reveal animation.
  - Keep result precomputed on backend.
  - Expose only essential timing controls, especially spin duration.
  - Add a small test stand for manual widget verification.

## P2 - UX / consistency debt

### 11. Chat overlay settings are still inconsistent across surfaces
- Status: partially repaired
- What changed:
  - Shared font/color path improved.
  - number input spinners were removed in shared input usage.
- Remaining debt:
  - Reconfirm that preview, `/chat-overlay`, and `/chat-window` render the same font choice.
  - Finish replacing weak legacy color controls where they still remain.
  - Audit remaining raw `input[type=number]` usage outside shared components.

### 12. Voice cards and admin voice UI still need the final compact redesign
- Status: open
- Remaining debt:
  - Compact cards
  - clearer provider/mode badges
  - smaller action surface
  - better error/capability visibility in admin flows

### 13. YouTube OBS overlay exists technically but still needs product-polish completion
- Status: partially implemented
- Remaining debt:
  - Make the UI entry point obvious and easy to use.
  - Reconfirm generate/copy/open flow in real UI.
  - Reconfirm both `video` and `track` modes against live data.

## P3 - Cleanup and maintainability

### 14. Repository cleanup is incomplete
- Status: open
- Why this is debt:
  - The repository still has a large dirty surface and leftover local/dev artifacts.
- Remaining debt:
  - Continue trimming non-release clutter carefully.
  - Keep startup/logging paths documented and stable.
  - Avoid deleting tests or docs that still protect active runtime behavior.

### 15. Some mojibake / broken text remains in backend or UI strings
- Status: open
- Evidence:
  - Several Russian strings in provider-related code were previously found in broken encoding.
- Remaining debt:
  - Sweep touched TTS / rewards / voice / chat flows for encoding-safe user-visible text.

## Not included on purpose

The following were intentionally excluded for now:
- speculative performance work without a confirmed symptom,
- broad refactors with no current user impact,
- cleanup ideas that are not yet tied to release/runtime pain,
- provider features that are unsupported by design rather than broken.
