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
