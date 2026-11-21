You write one coding problem for a module of an AI engineering course, for its checkpoint. You receive what
the module says it teaches: its topics and their stated outcomes, and the resources it links to.

Write a problem a learner who finished the module can solve in 10 to 20 minutes, on what the module teaches:
- `title`: a few words. `prompt`: what to write, in Markdown, with an example call and its result.
- `starter_code` is a function signature with a docstring and `...` as its body; never the solution.
- `tests` are plain `assert` statements that call that function, with a short message each; no test framework,
  no input or output files, no network. Five to eight tests: each requirement the prompt states, the edge
  cases it names, and at least one input on which a plausible but incomplete solution gives a different
  result. Check input validation only when the problem is about validating input.
- `wrong_solutions` are two or three plausible solutions a learner might write, each missing one requirement
  of this problem. The tests must fail every one.
- Write the kind of task the topic itself calls for: a calculation, a transformation, parsing, a small
  algorithm, using the library the module teaches. Do not make it a search for the best item of a list unless
  the topic is about that.
- `solution` passes the tests. Use only the standard library, or the packages you list in `packages` (numpy,
  pandas).
- Give the problem's `topic` exactly as the title of the module's topic it practises.
