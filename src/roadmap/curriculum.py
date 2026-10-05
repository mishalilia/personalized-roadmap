"""The curriculum as the planner sees it: modules in course order, each with the resources it links to."""

from enum import StrEnum

from pydantic import BaseModel


class Level(StrEnum):
    """One scale for a learner's level and for the difficulty the curriculum declares for a resource."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Resource(BaseModel):
    """External material a module links to. The material itself stays under its own licence."""

    title: str
    url: str
    type: str
    difficulty: Level
    duration: str
    note: str  # why the curriculum authors recommend it


class Module(BaseModel):
    """A learning unit of the curriculum, and the unit that a path includes or skips."""

    id: str
    title: str
    description: str
    section: list[str]  # labels of the sections the module sits in, outermost first
    url: str
    resources: list[Resource]
    prerequisites: list[str]  # as the curriculum authors state them, where they do
    # The authors' completion checklist, as Markdown. A learner who can already do all of
    # it may prove the module instead of studying it.
    checklist: list[str]

    @property
    def can_be_proved(self) -> bool:
        return bool(self.checklist)

    @property
    def full_title(self) -> str:
        return " › ".join([*self.section, self.title])


class Attribution(BaseModel):
    """What the licence requires us to credit: title, author, source and licence."""

    title: str
    author: str
    url: str
    licence: str
    licence_url: str


class Curriculum(BaseModel):
    version: str
    attribution: Attribution
    modules: list[Module]
