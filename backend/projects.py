"""Project-scoped storage for independent DocuMind workspaces."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.config import DATA_DIR, DOCS_DIR, INDEX_FILE, PROJECTS_DIR

GENERAL_PROJECT_ID = "general"
PROJECT_FILE = "project.json"


@dataclass(frozen=True)
class Project:
    identifier: str
    name: str
    documents_dir: Path
    index_file: Path
    created_at: str | None = None


def _safe_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48]
    if not identifier:
        raise ValueError("Project names need at least one letter or number.")
    return identifier


def _general_project() -> Project:
    return Project(GENERAL_PROJECT_ID, "General library", DOCS_DIR, INDEX_FILE)


def _from_directory(directory: Path) -> Project | None:
    metadata_path = directory / PROJECT_FILE
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        identifier = str(metadata["id"])
        name = str(metadata["name"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if _safe_identifier(identifier) != identifier:
        return None
    return Project(identifier, name, directory / "documents", directory / "index.json", metadata.get("created_at"))


def list_projects() -> list[Project]:
    PROJECTS_DIR.mkdir(exist_ok=True)
    projects = [_general_project()]
    for directory in sorted(PROJECTS_DIR.iterdir()):
        if directory.is_dir() and (project := _from_directory(directory)):
            projects.append(project)
    return projects


def get_project(identifier: str) -> Project:
    if identifier == GENERAL_PROJECT_ID:
        return _general_project()
    safe_identifier = _safe_identifier(identifier)
    if safe_identifier != identifier:
        raise ValueError("Project was not found.")
    project = _from_directory(PROJECTS_DIR / identifier)
    if not project:
        raise ValueError("Project was not found.")
    return project


def create_project(name: str) -> Project:
    clean_name = " ".join(name.strip().split())
    if not clean_name or len(clean_name) > 80:
        raise ValueError("Project names must be between 1 and 80 characters.")
    base_identifier = _safe_identifier(clean_name)
    PROJECTS_DIR.mkdir(exist_ok=True)
    identifier, suffix = base_identifier, 2
    while (PROJECTS_DIR / identifier).exists() or identifier == GENERAL_PROJECT_ID:
        identifier = f"{base_identifier}-{suffix}"
        suffix += 1

    directory = PROJECTS_DIR / identifier
    documents_dir = directory / "documents"
    documents_dir.mkdir(parents=True)
    created_at = datetime.now(UTC).isoformat()
    metadata = {"id": identifier, "name": clean_name, "created_at": created_at}
    (directory / PROJECT_FILE).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return Project(identifier, clean_name, documents_dir, directory / "index.json", created_at)


def delete_project(identifier: str) -> None:
    if identifier == GENERAL_PROJECT_ID:
        raise ValueError("The general library can't be removed.")
    project = get_project(identifier)
    shutil.rmtree(project.documents_dir.parent)


def project_summary(project: Project, chunks: int, indexed: bool, provider: str | None) -> dict[str, object]:
    return {
        "id": project.identifier,
        "name": project.name,
        "documents": len([item for item in project.documents_dir.iterdir() if item.is_file()]) if project.documents_dir.exists() else 0,
        "indexed": indexed,
        "chunks": chunks,
        "provider": provider,
        "created_at": project.created_at,
    }
