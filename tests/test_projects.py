"""Tests for project-scoped storage and identifier safety."""

import pytest

import backend.projects as projects_module
from backend.projects import create_project, get_project, list_projects


@pytest.fixture(autouse=True)
def isolated_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")


def test_create_project_generates_a_safe_identifier():
    project = create_project("My Cool Project!")

    assert project.identifier == "my-cool-project"
    assert project.documents_dir.exists()


def test_create_project_deduplicates_identifiers():
    first = create_project("Docs")
    second = create_project("Docs")

    assert first.identifier == "docs"
    assert second.identifier == "docs-2"


def test_create_project_rejects_blank_name():
    with pytest.raises(ValueError):
        create_project("   ")


def test_create_project_rejects_overlong_name():
    with pytest.raises(ValueError):
        create_project("x" * 81)


def test_get_project_rejects_path_traversal_identifiers():
    with pytest.raises(ValueError):
        get_project("../../etc")


def test_get_project_raises_for_unknown_project():
    with pytest.raises(ValueError):
        get_project("does-not-exist")


def test_get_project_general_does_not_require_a_directory():
    project = get_project("general")
    assert project.identifier == "general"


def test_list_projects_includes_general_and_created_projects():
    create_project("Alpha")

    identifiers = [project.identifier for project in list_projects()]

    assert "general" in identifiers
    assert "alpha" in identifiers
