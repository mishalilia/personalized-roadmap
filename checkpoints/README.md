# Checkpoints

One directory per curriculum version, `checkpoints/<version name>/<module id>.yaml`, for the versions in
[config/curriculum.yaml](../config/curriculum.yaml). A checkpoint is served only for the version it names.

- `python -m roadmap checkpoints <module id>` (or `--all`, and `--curriculum <version>` for an older one)
  writes a draft with the model: fifteen questions, and one coding problem for modules that teach programming.
- `python -m roadmap checkpoints --verify` runs every reference solution against its tests in a separate
  Python. The code comes from the checkpoint files, so read them first: generated code runs on your machine.
- A person who knows the topic checks every question: is the marked answer right, does the question ask the
  learner to apply an idea rather than recall it, does it stay within what the module teaches (Q-004). They
  fix or replace what fails, then set `status: reviewed` and `reviewed_by`.
- Generating again does not overwrite a reviewed file unless `--force` is given.

A learner sees five questions an attempt, with the options in a new order each time, and passes with four. A
failed attempt shows which answers were wrong and which topics to review, but not the right answers; those
appear after a pass. Then comes the coding problem, if there is one: the learner's code runs in their browser
(Pyodide) against the problem's tests.

The files here are drafts written by Claude during development, not by the generator, so that the checkpoint
flow can be shown: two modules for each version, with the same questions where the module did not change. They
are not reviewed. Questions are derived from the curriculum and are
licensed CC BY-NC-SA 4.0, like the rest of the curriculum-derived material in this repository.
