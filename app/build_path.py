"""Page: answer the questions, check the suggested level, and get a personal path."""

import streamlit as st

import path_view
from roadmap import (
    CHANGES_NOTICE,
    LearnerProfile,
    Level,
    LevelAssessment,
    Roadmap,
    Settings,
    load_profiles,
)

OWN_ANSWERS = "My own answers"
PATH = "path"  # where this page keeps its path in st.session_state


@st.cache_resource(show_spinner="Loading the curriculum…")
def load_roadmap() -> Roadmap:
    return Roadmap.from_settings(Settings())


@st.cache_resource
def load_example_profiles() -> dict[str, LearnerProfile]:
    return {
        profile.title: profile for profile in load_profiles(Settings().profiles_file)
    }


def main() -> None:
    roadmap = load_roadmap()

    st.title("Personalized Learning Roadmap", anchor=False)
    st.caption(
        "A personal path through a real curriculum: what to study, what to skip, and why."
    )
    if not roadmap.personalization_available:
        st.warning(
            "No language model is configured, so paths follow the course as written. "
            "Add LLM_API_KEY_GROQ or LLM_API_KEY_GOOGLE to `.env` to personalize them."
        )

    onboarding_step(roadmap)
    if "answers" in st.session_state:
        level_step(roadmap)
    if PATH in st.session_state:
        st.header("3 · Your path", anchor=False)
        path_view.show_path(PATH)
    curriculum = roadmap.curriculum
    path_view.attribution_footer(
        curriculum.attribution, curriculum.version, CHANGES_NOTICE
    )


def onboarding_step(roadmap: Roadmap) -> None:
    st.header("1 · About you", anchor=False)
    profiles = load_example_profiles()
    st.selectbox(
        "Answer the questions yourself, or start from an invented example learner",
        [OWN_ANSWERS, *profiles],
        key="profile_choice",
        on_change=fill_in_profile,
        args=(roadmap, profiles),
    )
    with st.form("onboarding"):
        for question in roadmap.questions:
            st.text_area(
                question.text,
                key=answer_key(question.id),
                placeholder=question.placeholder,
            )
        submitted = st.form_submit_button("Suggest my level", type="primary")

    if not submitted:
        return
    answers = {
        question.id: st.session_state[answer_key(question.id)]
        for question in roadmap.questions
    }
    if not any(answer.strip() for answer in answers.values()):
        st.error("Answer at least one question first.")
        return
    with st.spinner("Reading your answers…"):
        assessment = roadmap.assess_level(answers)
    st.session_state.answers = answers
    st.session_state.assessment = assessment
    st.session_state.level_choice = assessment.level if assessment else Level.BEGINNER
    st.session_state.pop(PATH, None)


def fill_in_profile(roadmap: Roadmap, profiles: dict[str, LearnerProfile]) -> None:
    profile = profiles.get(st.session_state.profile_choice)
    for question in roadmap.questions:
        st.session_state[answer_key(question.id)] = (
            profile.answers.get(question.id, "") if profile else ""
        )
    for stale in ("answers", "assessment", PATH):
        st.session_state.pop(stale, None)


def answer_key(question_id: str) -> str:
    return f"answer_{question_id}"


def level_step(roadmap: Roadmap) -> None:
    st.header("2 · Your level", anchor=False)
    assessment: LevelAssessment | None = st.session_state.assessment
    if assessment is None:
        st.info(
            "A level could not be suggested right now. Choose the one that fits you best."
        )
    else:
        st.markdown(
            f"Suggested level: **{assessment.level.capitalize()}** · "
            f"{assessment.confidence} confidence"
        )
        st.markdown("\n".join(f"- {point}" for point in assessment.evidence))
        st.caption(
            "This is a suggestion, not a verdict. If it is wrong, change it: "
            "your path is planned for the level you choose."
        )
    st.radio(
        "Plan my path for",
        list(Level),
        key="level_choice",
        format_func=str.capitalize,
        horizontal=True,
    )

    if st.button("Build my path", type="primary"):
        with st.spinner("Planning your path…"):
            path = roadmap.build_path(
                st.session_state.answers, st.session_state.level_choice, assessment
            )
        path_view.set_path(PATH, path)


main()
