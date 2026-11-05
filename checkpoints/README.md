# Checkpoints

One file per module, `<module id>.yaml`, for the curriculum version pinned in
[config/curriculum.yaml](../config/curriculum.yaml). The API serves a checkpoint only for that version.

- `python -m roadmap checkpoints generate <module id>` (or `--all`) writes a draft with the model.
- A person who knows the topic checks every question: is the marked answer right, does the question ask the
  learner to apply an idea rather than recall it, does it stay within what the module teaches (Q-004). They
  fix or replace what fails, then set `status: reviewed` and `reviewed_by`.
- Generating again does not overwrite a reviewed file unless `--force` is given.

A learner sees five questions an attempt and passes with four; a retake shows the other five.

The two files here are drafts written by Claude during development, not by the generator, so that the
checkpoint flow can be shown. They are not reviewed. Questions are derived from the curriculum and are
licensed CC BY-NC-SA 4.0, like the rest of the curriculum-derived material in this repository.
