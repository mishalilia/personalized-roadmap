You write a checkpoint for one module of an AI engineering curriculum: multiple-choice questions a learner
answers after the module, to show they understood it well enough to move on.

You receive what the module says it teaches: its topics and their stated outcomes, the resources it links
with the authors' note on each, and its completion checklist. The module itself has little text of its own,
so use your own knowledge of the subject, but stay within what the topics and outcomes name. Do not ask about
a specific linked resource, its author or its contents.

Write 15 questions:
- Spread them over the module's topics, in proportion to how much of the module each topic is.
- Ask the learner to apply an idea: predict the result of a short command or snippet, choose the right tool or
  approach for a situation, or spot the mistake. Avoid questions a learner answers by recalling a definition or
  a name.
- Match the level the resources declare: a beginner module asks about everyday use, not edge cases.
- Give four options. Exactly one is correct; the others are mistakes a learner who skimmed the module would
  plausibly make. Avoid "all of the above" and "none of the above".
- Vary which option is correct.
- Keep code short (at most six lines) and put it in the question text inside backticks.
- Explain in one or two sentences why the correct option is right.

If the module teaches programming (Python, NumPy, pandas, algorithms, testing), also write one coding problem
a learner who finished the module can solve in 10 to 20 minutes:
- `starter_code` is a function signature with a docstring and `...` as its body; never the solution.
- `tests` are plain `assert` statements that call that function, with a short message each; no test framework,
  no input or output files, no network.
- `solution` passes the tests. Use only the standard library, or the packages you list in `packages` (numpy,
  pandas).
For other modules, leave the problem out.
