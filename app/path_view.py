"""A path on screen: what to do with each module, the learner's changes, and the confirmation.

Shared by the pages. Each page keeps its path in st.session_state under its own key, so the
paths of different pages do not mix.
"""

from itertools import groupby

import streamlit as st

from roadmap import Attribution, Choice, LearningPath, PathItem


def show_path(state_key: str) -> None:
    path: LearningPath = st.session_state[state_key]
    if path.personalization_unavailable:
        st.warning(
            "Personalization was unavailable when this path was built, "
            "so it follows the course as written."
        )
    st.caption(
        "The planner only suggests. Change what you do with any module: "
        "your choice replaces its suggestion."
    )
    study, prove, skip, changed = st.columns(4)
    study.metric("To study", path.count(Choice.STUDY))
    prove.metric("To prove", path.count(Choice.PROVE))
    skip.metric("Skipped", path.count(Choice.SKIP))
    changed.metric(
        "Changed by you", sum(item.changed_by_learner for item in path.items)
    )

    sections = groupby(path.items, key=lambda item: " › ".join(item.module.section))
    for section, section_items in sections:
        items = list(section_items)
        if any(item.included for item in items):
            st.subheader(section, anchor=False)
            for item in items:
                _show_item(item, state_key)
        else:
            with st.expander(f"⏭ {section} · skipped"):
                for item in items:
                    _show_item(item, state_key)

    _confirmation(path, state_key)


def set_path(state_key: str, path: LearningPath) -> None:
    """Show a new path. Its decisions get new widgets, so no choice made on an earlier path
    can carry over: the browser keeps a widget's value for as long as its key stays the same.
    """
    version_key = f"{state_key}.version"
    st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
    st.session_state[state_key] = path


def attribution_footer(attribution: Attribution, version: str, changes: str) -> None:
    st.divider()
    st.caption(
        f"Learning content: [{attribution.title}]({attribution.url}) by "
        f"{attribution.author}, version {version[:7]}, licensed under "
        f"[{attribution.licence}]({attribution.licence_url}). {changes}"
    )


def _show_item(item: PathItem, state_key: str) -> None:
    module = item.module
    with st.container(border=True):
        title, control = st.columns([3, 2])
        title.markdown(
            f"**{module.title}**" if item.included else f":gray[**{module.title}**]"
        )
        options = list(Choice) if module.can_be_proved else [Choice.STUDY, Choice.SKIP]
        key = _choice_key(state_key, module.id)
        if key not in st.session_state:
            st.session_state[key] = item.choice
        control.radio(
            f"What to do with {module.title}",
            options,
            key=key,
            format_func=str.capitalize,
            horizontal=True,
            label_visibility="collapsed",
            on_change=_change_choice,
            args=(state_key, key, module.id),
        )
        st.caption(_planner_note(item))
        if item.choice is Choice.PROVE:
            st.markdown(
                "**Prove it instead of studying it.** If you can already do everything "
                "below, you do not need this module; if you cannot, switch to Study."
            )
            st.markdown("\n".join(f"- {check}" for check in module.checklist))
        with st.expander("Details"):
            st.caption(module.description)
            for resource in module.resources:
                st.markdown(
                    f"- [{resource.title}]({resource.url}) · {resource.type} · "
                    f"{resource.difficulty} · {resource.duration}  \n  {resource.note}"
                )
            st.caption(f"Module page: [{module.full_title}]({module.url})")


def _planner_note(item: PathItem) -> str:
    if not item.changed_by_learner:
        return item.reason
    return (
        f"You changed this. The planner's suggestion was to {item.suggested} it: "
        f"{item.reason}"
    )


def _confirmation(path: LearningPath, state_key: str) -> None:
    if not path.confirmed:
        st.button(
            "Confirm my path", type="primary", on_click=_confirm, args=(state_key,)
        )
        st.caption(
            "Review the path first. You can download it once you have confirmed it."
        )
        return
    st.success("Path confirmed. Any change you make now needs a new confirmation.")
    st.download_button(
        "Download the path as JSON",
        path.model_dump_json(indent=2),
        file_name="learning-path.json",
        mime="application/json",
    )


def _choice_key(state_key: str, module_id: str) -> str:
    version = st.session_state.get(f"{state_key}.version", 0)
    return f"{state_key}.{version}.choice.{module_id}"


def _change_choice(state_key: str, key: str, module_id: str) -> None:
    st.session_state[state_key] = st.session_state[state_key].with_choice(
        module_id, st.session_state[key]
    )


def _confirm(state_key: str) -> None:
    st.session_state[state_key] = st.session_state[state_key].confirm()
