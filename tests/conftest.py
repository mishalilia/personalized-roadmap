import os

import pytest
from helpers import FIXTURE_DOCS, ROOT, SITE_URL

from roadmap import Attribution, Curriculum, Question
from roadmap.docusaurus import parse_modules
from roadmap.onboarding import load_questions


@pytest.fixture
def curriculum() -> Curriculum:
    """A small invented course in the same Docusaurus format as the real one."""
    return Curriculum(
        version="test-version",
        attribution=Attribution(
            title="Example Curriculum",
            author="Example Authors",
            url="https://site.example",
            licence="CC BY-NC-SA 4.0",
            licence_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
        ),
        modules=parse_modules(FIXTURE_DOCS, SITE_URL),
    )


@pytest.fixture
def module_ids(curriculum: Curriculum) -> list[str]:
    return [module.id for module in curriculum.modules]


@pytest.fixture
def questions() -> list[Question]:
    return load_questions(ROOT / "config" / "onboarding.yaml")


# With ROADMAP_TEST_DATABASE_URL set to a PostgreSQL database that may be emptied, every store in every test
# uses it instead of a SQLite file: the whole suite then runs against PostgreSQL. As with SQLite, stores given
# the same file share a database and each ":memory:" one is a database of its own: here, a schema of its own,
# dropped when the test ends.
_POSTGRES_URL = os.environ.get("ROADMAP_TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
def _stores_on_postgres(monkeypatch):
    if not _POSTGRES_URL:
        yield
        return
    import psycopg

    from roadmap.database import PostgresDatabase

    opened: dict[str, PostgresDatabase] = {}
    schemas: list[str] = []

    def open_database(target):
        key = str(target)
        if key in opened and key != ":memory:":
            return opened[key]
        schema = f"test_{len(schemas)}"
        schemas.append(schema)
        with psycopg.connect(_POSTGRES_URL, autocommit=True) as connection:
            connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            connection.execute(f"CREATE SCHEMA {schema}")
        database = PostgresDatabase(
            f"{_POSTGRES_URL}?options=-csearch_path%3D{schema}", max_connections=4
        )
        opened[key if key != ":memory:" else schema] = database
        return database

    monkeypatch.setattr("roadmap.database.Database.open", staticmethod(open_database))
    yield
    for database in opened.values():
        database.close()
    with psycopg.connect(_POSTGRES_URL, autocommit=True) as connection:
        for schema in schemas:
            connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
