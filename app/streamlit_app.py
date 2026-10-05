"""Demo interface. Run from the repository root: `streamlit run app/streamlit_app.py`."""

import streamlit as st

st.set_page_config(page_title="Personalized Learning Roadmap", page_icon="🧭")
st.navigation(
    [
        st.Page("build_path.py", title="Build a path", icon="🧭", default=True),
        st.Page("saved_path.py", title="Open a saved path", icon="📂"),
    ]
).run()
