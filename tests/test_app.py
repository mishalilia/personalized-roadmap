"""The web interface: building a path, changing and confirming it, and opening a saved one."""

import pytest
import streamlit as st
from helpers import ROOT, FakeLLM, planner_response, study_all
from streamlit.testing.v1 import AppTest

from roadmap import Choice, Level, Roadmap

APP = str(ROOT / "app" / "streamlit_app.py")
LEVEL_ANSWER = {
    "level": "intermediate",
    "evidence": ["Three years of backend work"],
    "confidence": "medium",
}


@pytest.fixture
def app(monkeypatch, curriculum, questions, module_ids) -> AppTest:
    plan = planner_response(
        curriculum,
        {
            module_id: (Choice.SKIP if "speech" in module_id else Choice.STUDY, "Why.")
            for module_id in module_ids
        },
    )
    roadmap = Roadmap(curriculum, questions, FakeLLM(LEVEL_ANSWER, plan))
    monkeypatch.setattr(
        Roadmap, "from_settings", classmethod(lambda cls, settings: roadmap)
    )
    monkeypatch.chdir(ROOT)
    st.cache_resource.clear()
    return AppTest.from_file(APP, default_timeout=30).run()


def button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def choice_for(app: AppTest, module_id: str):
    """The radio with the learner's choice for a module."""
    [radio] = [r for r in app.radio if r.key and r.key.endswith(f".choice.{module_id}")]
    return radio


def metrics(app: AppTest) -> dict[str, str]:
    return {metric.label: metric.value for metric in app.metric}


def submit_example_answers(app: AppTest) -> None:
    profile_choice = app.selectbox(key="profile_choice")
    profile_choice.select(profile_choice.options[1]).run()
    app.button[0].click().run()  # submits the onboarding form


def test_demo_flow_plans_for_the_level_the_learner_chooses(app):
    submit_example_answers(app)
    assert app.radio(key="level_choice").value == Level.INTERMEDIATE

    app.radio(key="level_choice").set_value(Level.ADVANCED).run()
    button(app, "Build my path").click().run()

    assert not app.exception
    path = app.session_state["path"]
    assert path.level == Level.ADVANCED
    assert path.assessment.level == Level.INTERMEDIATE
    assert metrics(app) == {
        "To study": "5",
        "To prove": "0",
        "Skipped": "1",
        "Changed by you": "0",
    }
    assert "⏭ Tracks › Speech · skipped" in [
        expander.label for expander in app.expander
    ]


def test_learner_changes_the_path_and_confirms_it(app):
    submit_example_answers(app)
    button(app, "Build my path").click().run()

    choice_for(app, "tracks/speech/resources").set_value(Choice.STUDY).run()
    choice_for(app, "basics/terminal").set_value(Choice.PROVE).run()

    assert metrics(app) == {
        "To study": "5",
        "To prove": "1",
        "Skipped": "0",
        "Changed by you": "2",
    }
    # The checklist replaces the module for a learner who proves it.
    assert any("Search across files" in block.value for block in app.markdown)
    # A module without a checklist offers no way to prove it.
    assert choice_for(app, "basics/algebra").options == ["Study", "Skip"]
    assert not [b for b in app.button if b.label == "Download the path as JSON"]

    button(app, "Confirm my path").click().run()

    path = app.session_state["path"]
    assert path.confirmed
    assert {item.module.id for item in path.items if item.changed_by_learner} == {
        "tracks/speech/resources",
        "basics/terminal",
    }
    assert not app.exception


def test_a_saved_path_opens_without_asking_a_model(
    monkeypatch, tmp_path, curriculum, questions
):
    plan = study_all(
        curriculum, except_for={"basics/terminal": (Choice.PROVE, "You use the shell.")}
    )
    saved = Roadmap(curriculum, questions, FakeLLM(plan)).build_path({}, Level.BEGINNER)
    (tmp_path / "p1.json").write_text(saved.model_dump_json(), encoding="utf-8")
    model = FakeLLM()  # has no answers, so any question to it would fail the test
    roadmap = Roadmap(curriculum, questions, model)
    monkeypatch.setattr(
        Roadmap, "from_settings", classmethod(lambda cls, settings: roadmap)
    )
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.chdir(ROOT)
    st.cache_resource.clear()
    app = AppTest.from_file(APP, default_timeout=30).run()

    app.switch_page("saved_path.py").run()
    app.selectbox(key="saved_file").select_index(0).run()

    assert not app.exception
    assert metrics(app)["To prove"] == "1"
    assert any("Search across files" in block.value for block in app.markdown)
    choice_for(app, "basics/terminal").set_value(Choice.STUDY).run()
    assert metrics(app)["Changed by you"] == "1"
    assert model.prompts == []


def test_switching_between_saved_paths_keeps_working(
    monkeypatch, tmp_path, curriculum, questions
):
    for name, choice in (("a.json", Choice.PROVE), ("b.json", Choice.SKIP)):
        plan = study_all(curriculum, except_for={"basics/terminal": (choice, "Why.")})
        path = Roadmap(curriculum, questions, FakeLLM(plan)).build_path({}, None)
        (tmp_path / name).write_text(path.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.chdir(ROOT)
    st.cache_resource.clear()
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.switch_page("saved_path.py").run()

    app.selectbox(key="saved_file").select_index(0).run()
    choice_for(app, "basics/terminal").set_value(Choice.STUDY).run()
    app.selectbox(key="saved_file").select_index(1).run()
    choice_for(app, "basics/terminal").set_value(Choice.STUDY).run()

    assert not app.exception
    assert app.session_state["saved_path"].items[0].suggested is Choice.SKIP
    assert metrics(app)["Changed by you"] == "1"
