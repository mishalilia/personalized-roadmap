"""The curriculum as the planner sees it: modules in course order, each with the resources it links to."""

from enum import StrEnum

from pydantic import BaseModel, computed_field


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
    difficulty: Level | None = (
        None  # the current curriculum leaves it out of most resources
    )
    duration: str = ""
    note: str  # why the curriculum authors recommend it


class Hours(BaseModel):
    """A time estimate, as a range."""

    low: float
    high: float


class Topic(BaseModel):
    """A part of a module, as its authors head it, with the outcomes they list for it."""

    title: str
    outcomes: list[str] = []
    # The heading's id on the page, as its authors set it ("{#terminal}"), so a link can open the topic.
    anchor: str | None = None


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
    # The module's parts and their stated outcomes: what a checkpoint asks about. Paths saved before
    # checkpoints existed have none.
    topics: list[Topic] = []
    # The authors' estimate of the module's workload, or the sum of its resources' durations; None when
    # neither is stated.
    hours: Hours | None = None
    # For a capstone: what the project must solve and deliver, and its evaluation rubric, as Markdown. A review
    # of a submitted project grades against it, from the curriculum version the path was planned for.
    project_brief: str = ""

    @property
    def can_be_proved(self) -> bool:
        return bool(self.checklist)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_project(self) -> bool:
        """A capstone: the learner builds a project and submits it for review instead of a checkpoint."""
        return self.id.rsplit("/", 1)[-1] == "capstone"

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
    version: str  # the commit
    # The curriculum site's name for this version, such as "current" or "2026-10-06", where known.
    site_version: str | None = None
    attribution: Attribution
    modules: list[Module]
