import React, { useEffect, useState, type ReactNode } from "react";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import { message, type PathApi } from "./api";
import { MessageCircle } from "lucide-react";
import { askAssistant, handleSignedOut, setOpenProblem, setPath } from "./store";
import { Spinner } from "./ui";
import { Reply } from "./PathChat";
import { headingAnchor, type CodingProblem as Problem, type LearningPath } from "./model";
import { onCodeKey } from "./codeKeys";
import { noteError } from "./pageErrors";
import styles from "./path.module.css";

// Pyodide runs Python in the browser, so the learner's code never reaches a server. It is loaded from
// PYODIDE_URL (docusaurus.config.ts) the first time a learner runs a problem, and kept for the visit.
const DEFAULT_PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

type Pyodide = {
  loadPackage(names: string[]): Promise<void>;
  runPythonAsync(code: string): Promise<unknown>;
  setStdout(options: { batched: (text: string) => void }): void;
};

declare global {
  interface Window {
    loadPyodide?: (options: { indexURL: string }) => Promise<Pyodide>;
  }
}

let pyodide: Promise<Pyodide> | null = null;

function loadPython(indexURL: string): Promise<Pyodide> {
  pyodide ??= new Promise<Pyodide>((resolve, reject) => {
    const start = () => window.loadPyodide!({ indexURL }).then(resolve, reject);
    if (window.loadPyodide) return start();
    const script = document.createElement("script");
    script.src = `${indexURL}pyodide.js`;
    script.onload = start;
    script.onerror = () => reject(new Error("Python could not be loaded in this browser."));
    document.head.appendChild(script);
  }).catch((error) => {
    pyodide = null; // let the learner try again
    throw error;
  });
  return pyodide;
}

// One test as the learner sees it: its message, or its code when it has none, and whether it passed.
export type TestResult = { label: string; code: string; ok: boolean; error?: string };
type Run = { ok: boolean; output: string; tests: TestResult[]; setupError?: string; error?: string };

// Runs the learner's code, then each top-level statement of the tests on its own, so one failing assert does
// not hide the others. Statements that are not asserts (imports, helpers) count only when they fail.
const HARNESS = `
import ast, json
def _run(code, tests):
    namespace = {}
    setup = None
    try:
        exec(compile(code, "solution.py", "exec"), namespace)
    except BaseException as error:
        setup = f"{type(error).__name__}: {error}"
    results = []
    for node in ast.parse(tests).body:
        source = ast.get_source_segment(tests, node) or ""
        # A test is any statement with an assert in it: a plain assert, or one inside a try or a loop.
        asserts = [inner for inner in ast.walk(node) if isinstance(inner, ast.Assert)]
        message = next((a.msg.value for a in asserts if isinstance(a.msg, ast.Constant)), None)
        label = message or source
        if setup:
            results.append({"label": label, "code": source, "ok": False, "error": "your code did not run"})
            continue
        try:
            exec(compile(ast.Module([node], []), "tests", "exec"), namespace)
            if asserts:
                results.append({"label": label, "code": source, "ok": True})
        except AssertionError as error:
            results.append({"label": label, "code": source, "ok": False, "error": f"AssertionError: {error}" if str(error) else "AssertionError"})
        except BaseException as error:
            results.append({"label": label, "code": source, "ok": False, "error": f"{type(error).__name__}: {error}"})
    return json.dumps({"setup": setup, "results": results})
`;

async function runTests(python: Pyodide, problem: Problem, code: string): Promise<Run> {
  let output = "";
  python.setStdout({ batched: (text) => (output += `${text}\n`) });
  if (problem.packages.length) await python.loadPackage(problem.packages);
  const raw = await python.runPythonAsync(
    `${HARNESS}\n_run(${JSON.stringify(code)}, ${JSON.stringify(problem.tests)})`,
  );
  const result = JSON.parse(String(raw)) as { setup: string | null; results: TestResult[] };
  const failed = result.results.filter((test) => !test.ok);
  const ok = !result.setup && failed.length === 0;
  return {
    ok,
    output,
    tests: result.results,
    setupError: result.setup ?? undefined,
    error: result.setup ?? (failed[0] ? `${failed[0].error}` : undefined),
  };
}

// The tests' top-level statements, as Python's own parser cuts them for the run: a statement starts at a line
// that is not indented while no bracket is open, and continues over indented or bracketed lines and over the
// clauses of a try or an if ("except", "else", "elif", "finally").
export function testStatements(tests: string): string[] {
  const statements: string[] = [];
  let depth = 0;
  const clause = /^(except\b|else\s*:|elif\b|finally\s*:)/;
  for (const line of tests.split("\n")) {
    if (!line.trim()) continue;
    if (depth === 0 && !/^\s/.test(line) && !(clause.test(line) && statements.length)) statements.push(line);
    else if (statements.length) statements[statements.length - 1] += `\n${line}`;
    else statements.push(line);
    // Brackets inside string literals do not count.
    for (const char of line.replace(/(["'])(?:\\.|(?!\1).)*\1/g, "")) {
      if ("([{".includes(char)) depth++;
      else if (")]}".includes(char)) depth = Math.max(0, depth - 1);
    }
  }
  return statements;
}

// What the tests said, in a few lines, for the assistant.
export function runSummary(run: Run): string {
  const lines = run.setupError ? [`Your code did not run: ${run.setupError}`] : [];
  for (const test of run.tests) lines.push(`${test.ok ? "passed" : "FAILED"}: ${test.code}${test.ok ? "" : ` (${test.error})`}`);
  if (run.output) lines.push(`Printed: ${run.output.slice(0, 300)}`);
  return lines.join("\n").slice(0, 1000);
}

export default function CodingProblem({
  api,
  path,
  moduleId,
  practice = false,
}: {
  api: PathApi;
  path: LearningPath;
  moduleId: string;
  // The module is already passed: the learner solves the problem again for practice, and nothing is recorded.
  practice?: boolean;
}): ReactNode {
  const { siteConfig } = useDocusaurusContext();
  const configured = siteConfig.customFields?.pyodideUrl;
  const indexURL = typeof configured === "string" && configured ? configured : DEFAULT_PYODIDE_URL;
  const [problem, setProblem] = useState<Problem | null>(null);
  const [code, setCode] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "running" | "solved">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .problem(moduleId, path.curriculum_version)
      .then((found) => {
        setProblem(found);
        setCode(found.starter_code);
      })
      .catch((reason: unknown) => setError(message(reason)));
  }, [api, moduleId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function check() {
    if (!problem) return;
    setError(null);
    setRun(null);
    try {
      setState("loading");
      const python = await loadPython(indexURL);
      setState("running");
      const result = await runTests(python, problem, code);
      setRun(result);
      if (result.ok && practice) {
        setState("solved");
      } else if (result.ok) {
        const solved = await api.solved(moduleId);
        setState("solved");
        setPath(solved);
      } else {
        setState("idle");
      }
    } catch (reason) {
      if (handleSignedOut(reason)) return setState("idle");
      const shown = reason instanceof Error && !("status" in reason) ? reason.message : message(reason);
      noteError(shown);
      setError(shown);
      setState("idle");
    }
  }

  // While the problem is on the page, the assistant can read the code and the last run with any question.
  useEffect(() => {
    if (!problem) return;
    setOpenProblem({ moduleId, code, lastRun: run ? runSummary(run) : null });
  }, [problem, moduleId, code, run]);
  useEffect(() => () => setOpenProblem(null), []);

  const solved = state === "solved";

  if (error && !problem) return <p className={styles.error}>{error}</p>;
  if (!problem)
    return (
      <p className={styles.muted}>
        <Spinner /> Loading the coding problem…
      </p>
    );

  return (
    <div className={styles.problem}>
      <div className={styles.problemHead}>
        <span className={styles.eyebrow}>Coding problem</span>
        <strong>{problem.title}</strong>
        {problem.topic && (
          <span className={styles.muted}>
            Practice for{" "}
            <a href={`#${problem.topic_anchor ?? headingAnchor(problem.topic)}`}>
              {problem.topic.replace(/^\d+\.\s*/, "")}
            </a>
          </span>
        )}
      </div>
      <div className={styles.problemPrompt}>
        <Reply text={problem.prompt} />
      </div>
      <div className={styles.tests}>
        <span className={styles.testsTitle}>The tests your code must pass</span>
        <pre className={styles.code}>
          {testStatements(problem.tests).map((statement, index) => {
            const result = solved ? { ok: true } : run?.tests.find((test) => test.code === statement);
            return (
              <span key={index} className={styles.testLine} data-ok={result ? result.ok : undefined}>
                <span className={styles.testMark} aria-label={result ? (result.ok ? "passes" : "fails") : undefined}>
                  {result ? (result.ok ? "✓" : "✗") : ""}
                </span>
                {statement.replace(/^assert\s+/, "")}
              </span>
            );
          })}
        </pre>
      </div>
      <label className={styles.editor}>
        <span className={styles.editorBar}>
          <span>solution.py</span>
          <span className={styles.muted}>Runs in your browser; your code is not sent anywhere.</span>
        </span>
        <textarea
          className={styles.code}
          spellCheck={false}
          aria-label="Your code"
          rows={Math.max(8, code.split("\n").length + 1)}
          value={code}
          disabled={state === "solved"}
          onChange={(event) => setCode(event.target.value)}
          onKeyDown={onCodeKey}
        />
      </label>
      {state === "solved" ? (
        <p className={styles.success} role="status">
          {practice ? "✓ All tests pass." : "✓ All tests pass. The module counts as completed."}
        </p>
      ) : (
        <div className={styles.submitRow}>
          {run && !run.ok ? (
            <span className={styles.failedRun}>
              <span className={styles.error} role="status">
                {run.setupError
                  ? `Your code did not run: ${run.setupError}`
                  : `Not yet: ${run.tests.filter((test) => test.ok).length} of ${run.tests.length} tests pass`}
              </span>
              <button
                type="button"
                className={styles.ghostSm}
                onClick={() =>
                  // The question goes into the chat's box for the learner to send or change; the code and the
                  // run of the tests go with it anyway, while the problem is open.
                  askAssistant({ text: "Why does my solution not pass yet?", moduleId })
                }
              >
                <MessageCircle size={14} aria-hidden /> Ask the assistant
              </button>
            </span>
          ) : (
            <span />
          )}
          <button
            type="button"
            className={styles.primary}
            disabled={state !== "idle"}
            onClick={() => void check()}
          >
            {state !== "idle" && <Spinner />}
            {state === "loading"
              ? "Loading Python…"
              : state === "running"
                ? "Running the tests…"
                : "Run the tests"}
          </button>
        </div>
      )}
      {run?.output && <pre className={styles.code}>{run.output}</pre>}
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
