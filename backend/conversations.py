"""Persistent, project-scoped conversation history for the portal."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.projects import Project


class ConversationStore:
    def __init__(self, project: Project, path: Path | None = None) -> None:
        self.path = path or project.index_file.with_name("chats.json")

    def _load(self) -> dict[str, object]:
        if not self.path.exists():
            return {"chats": []}
        with self.path.open(encoding="utf-8") as file:
            return json.load(file)

    def _save(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
        temporary.replace(self.path)

    @staticmethod
    def _summary(chat: dict[str, object]) -> dict[str, object]:
        return {key: chat.get(key) for key in ("id", "title", "created_at", "updated_at")}

    def list(self) -> list[dict[str, object]]:
        chats = self._load().get("chats", [])
        return [self._summary(chat) for chat in sorted(chats, key=lambda chat: str(chat.get("updated_at", "")), reverse=True)]

    def create(self) -> dict[str, object]:
        payload = self._load()
        timestamp = datetime.now(UTC).isoformat()
        chat: dict[str, object] = {
            "id": uuid4().hex,
            "title": "New chat",
            "created_at": timestamp,
            "updated_at": timestamp,
            "messages": [],
        }
        payload["chats"].append(chat)
        self._save(payload)
        return chat

    def get(self, identifier: str) -> dict[str, object]:
        for chat in self._load().get("chats", []):
            if chat.get("id") == identifier:
                return chat
        raise ValueError("Chat was not found in this project.")

    def append_exchange(self, identifier: str, question: str, answer: str, sources: list[dict[str, object]], evaluation: dict[str, object]) -> dict[str, object]:
        payload = self._load()
        for chat in payload["chats"]:
            if chat.get("id") != identifier:
                continue
            if not chat["messages"]:
                chat["title"] = question.strip().replace("\n", " ")[:64] or "New chat"
            chat["messages"].extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer, "sources": sources, "evaluation": evaluation},
                ]
            )
            chat["updated_at"] = datetime.now(UTC).isoformat()
            self._save(payload)
            return chat
        raise ValueError("Chat was not found in this project.")
