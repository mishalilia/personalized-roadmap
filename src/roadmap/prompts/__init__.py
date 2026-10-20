"""Model instructions, kept as Markdown files so they can be edited without touching code.

The JSON format of each answer is not described here: the client appends the schema of the response model.
"""

from importlib.resources import files


def load(name: str) -> str:
    return files(__name__).joinpath(f"{name}.md").read_text(encoding="utf-8")
