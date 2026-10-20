"""Page: open a path saved as JSON. Nothing is sent to a model."""

from pathlib import Path

import streamlit as st
from pydantic import ValidationError

import path_view
from roadmap import LearningPath, Settings

PATH = "saved_path"  # where this page keeps its path in st.session_state
LOAD_ERROR = "saved_path_error"


def main() -> None:
    st.title("Open a saved path", anchor=False)
    st.caption(
        "A path saved as JSON: one you downloaded, or one the command line wrote. "
        "Nothing is sent to a model, so this costs no quota."
    )
    saved_dir = Settings().output_dir
    files = sorted(saved_dir.rglob("*.json")) if saved_dir.exists() else []
    st.selectbox(
        f"Saved in {saved_dir}/",
        files,
        index=None,
        key="saved_file",
        format_func=lambda file: file.relative_to(saved_dir).as_posix(),
        placeholder="Choose a file",
        on_change=open_saved_file,
    )
    st.file_uploader(
        "Or open a file", type="json", key="uploaded_file", on_change=open_upload
    )

    if error := st.session_state.get(LOAD_ERROR):
        st.error(error)
    if PATH in st.session_state:
        path: LearningPath = st.session_state[PATH]
        show_level(path)
        path_view.show_path(PATH)
        path_view.attribution_footer(
            path.attribution, path.curriculum_version, path.changes
        )


def open_saved_file() -> None:
    file: Path | None = st.session_state.saved_file
    if file is not None:
        load(file.read_text(encoding="utf-8"))


def open_upload() -> None:
    upload = st.session_state.uploaded_file
    if upload is not None:
        load(upload.getvalue().decode("utf-8"))


def load(text: str) -> None:
    try:
        path_view.set_path(PATH, LearningPath.model_validate_json(text))
        st.session_state.pop(LOAD_ERROR, None)
    except ValidationError:
        st.session_state.pop(PATH, None)
        st.session_state[LOAD_ERROR] = (
            "This file is not a path, or an older version of the app saved it."
        )


def show_level(path: LearningPath) -> None:
    planned_for = path.level.capitalize() if path.level else "no level"
    st.markdown(f"Planned for: **{planned_for}**")
    if path.assessment is not None:
        st.caption(
            f"The model suggested {path.assessment.level} "
            f"({path.assessment.confidence} confidence): "
            + "; ".join(path.assessment.evidence)
        )


main()
