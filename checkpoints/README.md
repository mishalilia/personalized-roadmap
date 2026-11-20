# Checkpoints

One directory per curriculum version, `checkpoints/<version name>/<module id>.yaml`, for the versions in
[config/curriculum.yaml](../config/curriculum.yaml). A checkpoint is served only for the version it names.

- `python -m roadmap checkpoints <module id>` (or `--all`, and `--curriculum <version>` for an older one)
  writes a draft with the model: a pool of multiple-choice questions and two open questions per topic, and a
  coding problem per topic for modules that teach programming, with wrong solutions its tests must reject.
- `python -m roadmap checkpoints --verify` runs every reference solution against its tests in a separate
  Python. The code comes from the checkpoint files, so read them first: generated code runs on your machine.
- A person who knows the topic checks every question: is the marked answer right, does the question ask the
  learner to apply an idea rather than recall it, does it stay within what the module teaches (Q-004), and is
  its `topic` one of the module's topics (a failed attempt sends the learner back to it). For a coding problem:
  do the tests check the task, and does the starter code leave the solution out. They fix or replace what
  fails, then set `status: reviewed` and `reviewed_by`.
- Generating again does not overwrite a reviewed file unless `--force` is given.

A learner sees five questions an attempt from the topics they did not skip — four multiple-choice and, where
the checkpoint has them, one open question marked by the model against a rubric — and passes with four. Options
come in a new order each time, and the next attempt takes other questions. A failed attempt shows which answers
were wrong and which topics to review, not the right answers; those appear after a pass. Then comes the coding
problem, if there is one, run in the learner's browser (Pyodide) against its tests. A learner can report a wrong
question; reviewers see the report on the site.

What is here now, reviewed by Li Mikhail (`status: reviewed`):

- `current/`: 13 of the 20 modules, generated with gpt-6-luna: 15–56 multiple-choice questions (up to eight per
  topic), two open questions per topic, and 1–5 coding problems in every module except Data Science. Data
  Manipulation's first ten questions were written by Claude during development.
- `2026-10-06/`: Terminal & Algorithmic Basics and Data Manipulation, written by Claude during development: ten
  questions and a coding problem each.
- No checkpoint on purpose: the five capstones, which are projects, and the two elective modules, where each
  learner picks different options, so one set of questions would not fit them.

Questions are derived from the curriculum and are licensed CC BY-NC-SA 4.0, like the rest of the
curriculum-derived material in this repository.
