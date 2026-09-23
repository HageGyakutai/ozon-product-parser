import subprocess
from types import SimpleNamespace

import pytest

from ozon_parser import database_runtime


def test_prepare_database_does_not_start_docker_when_database_is_healthy(monkeypatch):
    calls = []
    monkeypatch.setattr(database_runtime, "_database_is_available", lambda engine: True)
    monkeypatch.setattr(
        database_runtime,
        "_start_postgres",
        lambda: pytest.fail("Docker must not start for a healthy database"),
    )
    monkeypatch.setattr(database_runtime, "_apply_migrations", lambda: calls.append("migrate"))

    database_runtime.prepare_database(object())

    assert calls == ["migrate"]


def test_prepare_database_starts_docker_then_applies_migrations(monkeypatch):
    availability = iter([False, True, True])
    calls = []
    monkeypatch.setattr(
        database_runtime,
        "_database_is_available",
        lambda engine: next(availability),
    )
    monkeypatch.setattr(database_runtime, "_start_postgres", lambda: calls.append("start"))
    monkeypatch.setattr(database_runtime, "_apply_migrations", lambda: calls.append("migrate"))

    database_runtime.prepare_database(object())

    assert calls == ["start", "migrate"]


def test_prepare_database_can_disable_automatic_docker_start(monkeypatch):
    monkeypatch.setattr(database_runtime, "_database_is_available", lambda engine: False)
    monkeypatch.setattr(
        database_runtime,
        "_start_postgres",
        lambda: pytest.fail("Docker must be disabled"),
    )

    with pytest.raises(RuntimeError, match="--no-start-database"):
        database_runtime.prepare_database(object(), auto_start=False)


def test_start_postgres_uses_compose_health_wait(monkeypatch):
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(database_runtime.subprocess, "run", run)

    database_runtime._start_postgres()

    assert captured["command"] == [
        "docker",
        "compose",
        "up",
        "-d",
        "--wait",
        "postgres",
    ]
    assert captured["cwd"] == database_runtime.PROJECT_ROOT
    assert captured["check"] is True


def test_start_postgres_reports_compose_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(database_runtime.subprocess, "run", fail)

    with pytest.raises(RuntimeError, match="could not start"):
        database_runtime._start_postgres()
