import logging
import subprocess
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from alembic import command

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _database_is_available(engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


def _start_postgres() -> None:
    LOGGER.info("PostgreSQL is unavailable; starting Docker Compose service")
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait", "postgres"],
            cwd=PROJECT_ROOT,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "PostgreSQL is unavailable and Docker was not found. "
            "Start PostgreSQL manually or install Docker Compose."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "PostgreSQL is unavailable and Docker Compose could not start it"
        ) from exc


def _apply_migrations() -> None:
    LOGGER.info("Applying Alembic migrations")
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")


def prepare_database(engine, *, auto_start: bool = True) -> None:
    if not _database_is_available(engine):
        if not auto_start:
            raise RuntimeError(
                "PostgreSQL is unavailable. Start it before running with "
                "--no-start-database."
            )
        _start_postgres()
        if not _database_is_available(engine):
            raise RuntimeError("PostgreSQL did not become available after Docker startup")
    else:
        LOGGER.info("PostgreSQL connection is healthy")

    _apply_migrations()

    if not _database_is_available(engine):
        raise RuntimeError("PostgreSQL health check failed after migrations")
