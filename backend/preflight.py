"""Verifies the prerequisites needed to run the DocuMind portal."""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCKER_INSTALL_URL = "https://www.docker.com/products/docker-desktop/"
MINIMUM_PYTHON = (3, 11)
REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "dotenv",
    "psycopg",
    "pgvector",
    "google.genai",
    "openai",
    "pypdf",
    "numpy",
]


def _status(label: str, message: str) -> None:
    print("  [{}] {}".format(label, message))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass


def _missing_modules() -> list[str]:
    missing = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    return missing


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _docker_engine_running() -> bool:
    try:
        completed = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _database_endpoint(database_url: str) -> tuple[str, int]:
    parsed = urlparse(database_url)
    return parsed.hostname or "localhost", parsed.port or 5432


def main() -> int:
    print("DocuMind prerequisite check")
    print("")

    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < MINIMUM_PYTHON:
        errors.append(
            "Python {}.{}+ is required, but this interpreter is {}.{}.".format(
                MINIMUM_PYTHON[0], MINIMUM_PYTHON[1], sys.version_info[0], sys.version_info[1]
            )
        )
    else:
        _status("OK", "Python {}.{} detected".format(sys.version_info[0], sys.version_info[1]))

    missing = _missing_modules()
    if missing:
        errors.append(
            "Missing Python packages: {}.\n         Install them with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt".format(
                ", ".join(missing)
            )
        )
    else:
        _status("OK", "Python dependencies are installed")

    _load_env()

    if not (PROJECT_ROOT / ".env").exists():
        warnings.append("No .env file found. Copy .env.example to .env and add your API keys.")

    if os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip():
        _status("OK", "At least one LLM provider key is configured")
    else:
        warnings.append(
            "No GEMINI_API_KEY or OPENAI_API_KEY set. The Gemini and OpenAI providers will not work; "
            "the Claude Pro (CLI) provider still works when the claude command is installed."
        )

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        host, port = _database_endpoint(database_url)
        if not _command_exists("docker"):
            errors.append(
                "DATABASE_URL is set, so this project needs Docker, but the docker command was not found.\n"
                "         Install Docker Desktop: {}\n"
                "         Or comment out DATABASE_URL in .env to use the local JSON store (no Docker required).".format(
                    DOCKER_INSTALL_URL
                )
            )
        elif not _docker_engine_running():
            errors.append(
                "Docker is installed but its engine is not running.\n"
                "         Start Docker Desktop, wait for it to finish starting, then run: docker compose up -d\n"
                "         Or comment out DATABASE_URL in .env to use the local JSON store (no Docker required)."
            )
        elif not _tcp_reachable(host, port):
            errors.append(
                "Docker is running but Postgres is not reachable at {}:{}.\n"
                "         Start the database with: docker compose up -d".format(host, port)
            )
        else:
            _status("OK", "Docker is running and Postgres is reachable at {}:{}".format(host, port))
    else:
        _status("INFO", "DATABASE_URL is not set; using the local JSON store (Docker not required)")

    print("")
    for message in warnings:
        _status("WARN", message)
    for message in errors:
        _status("FAIL", message)
    print("")

    if errors:
        print("Prerequisite check failed. Resolve the items marked FAIL above, then run this again.")
        return 1
    if warnings:
        print("Prerequisite check passed with warnings.")
        return 0
    print("All prerequisites satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
