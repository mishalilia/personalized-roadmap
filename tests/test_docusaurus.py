from helpers import SITE_URL

from roadmap import Curriculum, Level, Module


def module(curriculum: Curriculum, module_id: str) -> Module:
    return next(module for module in curriculum.modules if module.id == module_id)


def test_modules_follow_the_sidebar_and_leave_out_overview_pages(curriculum):
    assert [module.id for module in curriculum.modules] == [
        "basics/terminal",
        "basics/algebra",
        "tracks/speech/resources",  # same position as vision, so file-name order decides
        "tracks/vision/resources",
        "tracks/vision/capstone",
        "tracks/notes",  # no position, so it comes last
    ]


def test_urls_drop_number_prefixes_and_keep_slugs(curriculum):
    assert module(curriculum, "basics/terminal").url == f"{SITE_URL}/basics/01-terminal"
    assert module(curriculum, "basics/algebra").url == f"{SITE_URL}/basics/algebra"


def test_sections_come_from_category_labels(curriculum):
    capstone = module(curriculum, "tracks/vision/capstone")
    assert capstone.section == ["Tracks", "Vision"]
    assert capstone.full_title == "Tracks › Vision › Capstone"


def test_resource_cards_are_read_with_all_their_fields(curriculum):
    [resource] = module(curriculum, "basics/terminal").resources
    assert resource.title == "Shell in ten minutes"
    assert resource.url == "https://video.example.com/watch?v=abc&list=xyz"
    assert resource.type == "video"
    assert resource.difficulty == Level.BEGINNER
    assert resource.duration == "10 min"
    assert resource.note == "A short first look at the shell."


def test_resource_note_falls_back_to_the_description(curriculum):
    [resource] = module(curriculum, "basics/algebra").resources
    assert resource.note == "Uses description instead of why."


def test_prerequisites_are_read_as_plain_text_ignoring_code_blocks(curriculum):
    assert module(curriculum, "tracks/vision/capstone").prerequisites == [
        "Python programming (intermediate level)",
        "Familiarity with NumPy arrays",
        "OpenCV basics",
    ]
    assert module(curriculum, "basics/terminal").prerequisites == []


def test_checklists_keep_their_markdown_and_only_the_tick_boxes(curriculum):
    assert module(curriculum, "basics/terminal").checklist == [
        "Search across files with **grep**.",
        "Pass the [shell quiz](https://quiz.example.com/shell) with at least 80%.",
    ]
    # Authors word the heading differently; plain bullets next to the boxes are not checks.
    assert module(curriculum, "tracks/notes").checklist == ["Explain what a note is."]
    assert module(curriculum, "basics/algebra").checklist == []
