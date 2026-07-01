"""In-memory skip vote tracking for the active YouTube queue runtime."""

from __future__ import annotations

from threading import Lock


class SkipVoteStore:
    """Store votes by channel owner and current queue item."""

    def __init__(self) -> None:
        self._votes: dict[int, dict[str, set[str]]] = {}
        self._lock = Lock()

    @staticmethod
    def _normalize_video_key(video_id: str | int | None) -> str | None:
        if video_id is None:
            return None
        return str(video_id)

    @staticmethod
    def _normalize_voter(voter_name: str | int | None) -> str:
        return str(voter_name or "").strip().lower()

    def get_vote_count(self, owner_id: int, video_id: str | int | None) -> int:
        video_key = self._normalize_video_key(video_id)
        if not video_key:
            return 0
        with self._lock:
            return len(self._votes.get(owner_id, {}).get(video_key, set()))

    def add_vote(self, owner_id: int, video_id: str | int, voter_name: str | int | None) -> tuple[int, bool]:
        video_key = self._normalize_video_key(video_id)
        voter_key = self._normalize_voter(voter_name)
        if not video_key or not voter_key:
            return 0, False

        with self._lock:
            channel_votes = self._votes.setdefault(owner_id, {})
            if video_key not in channel_votes:
                # Keep only the active queue item for this channel owner.
                channel_votes = {video_key: set()}
                self._votes[owner_id] = channel_votes

            votes = channel_votes[video_key]
            if voter_key in votes:
                return len(votes), False

            votes.add(voter_key)
            return len(votes), True

    def clear_owner(self, owner_id: int) -> None:
        with self._lock:
            self._votes.pop(owner_id, None)

    def clear_video(self, owner_id: int, video_id: str | int | None) -> None:
        video_key = self._normalize_video_key(video_id)
        if not video_key:
            return
        with self._lock:
            channel_votes = self._votes.get(owner_id)
            if not channel_votes:
                return
            channel_votes.pop(video_key, None)
            if not channel_votes:
                self._votes.pop(owner_id, None)


skip_vote_store = SkipVoteStore()
