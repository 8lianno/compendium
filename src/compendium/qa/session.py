"""Conversation session — history persistence across turns."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ConversationSession:
    """Manages a single conversation session with turn history.

    Sessions persist to disk so they survive app restarts within the same day.
    """

    MAX_TURNS = 20

    def __init__(self, session_id: str, storage_dir: Path | None = None) -> None:
        self.session_id = session_id
        self.messages: list[dict[str, str]] = []
        self.created_at = datetime.now(UTC).isoformat()
        self._storage_dir = storage_dir

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        # Trim to max turns (each turn = user + assistant = 2 messages)
        max_messages = self.MAX_TURNS * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

        self._persist()

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self._persist()

    def _persist(self) -> None:
        """Save session to disk."""
        if self._storage_dir is None:
            return
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        path = self._storage_dir / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "messages": self.messages,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, session_id: str, storage_dir: Path) -> ConversationSession:
        """Load an existing session or create a new one."""
        path = storage_dir / f"{session_id}.json"
        session = cls(session_id, storage_dir)
        if path.exists():
            data = json.loads(path.read_text())
            session.messages = data.get("messages", [])
            session.created_at = data.get("created_at", session.created_at)
        return session

    @classmethod
    def list_sessions(cls, storage_dir: Path) -> list[dict]:
        """List all saved sessions."""
        if not storage_dir.exists():
            return []
        sessions = []
        for path in sorted(storage_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                sessions.append(
                    {
                        "session_id": data["session_id"],
                        "created_at": data.get("created_at", ""),
                        "message_count": len(data.get("messages", [])),
                    }
                )
            except Exception:
                continue
        return sessions
