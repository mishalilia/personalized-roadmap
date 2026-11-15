import React, { useEffect, useState, type ReactNode } from "react";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import { ApiError, type PathApi } from "./api";
import { InlineMarkdown } from "./InlineMarkdown";
import type { CodingProblem as Problem, LearningPath } from "./model";
import styles from "./PersonalPath.module.css";

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

type Run = { ok: true; output: string } | { ok: false; output: string; error: string };

// The learner's code and the tests run in a fresh namespace each time.
async function runTests(python: Pyodide, problem: Problem, code: string): Promise<Run> {
  let output = "";
  python.setStdout({ batched: (text) => (output += `${text}\n`) });
  if (problem.packages.length) await python.loadPackage(problem.packages);
  const program = [
    "namespace = {}",
    `exec(${JSON.stringify(code)}, namespace)`,
    `exec(${JSON.stringify(problem.tests)}, namespace)`,
  ].join("\n");
  try {
    await python.runPythonAsync(program);
    return { ok: true, output };
  } catch (error) {
    const text = String(error);
    // The last line of a Python traceback names the failed assert or the error.
    const last = text.trim().split("\n").filter(Boolean).pop() ?? text;
    return { ok: false, output, error: last };
  }
}

export default function CodingProblem({
  api,
  path,
  moduleId,
  onSolved,
}: {
  api: PathApi;
  path: LearningPath;
  moduleId: string;
  onSolved: (path: LearningPath) => void;
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
      if (result.ok) {
        onSolved(await api.solved(path, moduleId));
        setState("solved");
      } else {
        setState("idle");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : message(reason));
      setState("idle");
    }
  }

  if (error && !problem) return <p className={styles.error}>{error}</p>;
  if (!problem) return <p className={styles.small}>Loading the coding problem…</p>;

  return (
    <div className={styles.problem}>
      <strong>Coding problem: {problem.title}</strong>
      <div className={styles.small}>
        {problem.prompt.split("\n\n").map((paragraph, index) => (
          <p key={index}>
            <InlineMarkdown text={paragraph} />
          </p>
        ))}
      </div>
      <label className={styles.question}>
        <span className={styles.small}>Your code</span>
        <textarea
          className={styles.code}
          spellCheck={false}
          rows={Math.max(8, code.split("\n").length + 1)}
          value={code}
          disabled={state === "solved"}
          onChange={(event) => setCode(event.target.value)}
          onKeyDown={(event) => {
            // Tab indents instead of leaving the editor.
            if (event.key !== "Tab") return;
            event.preventDefault();
            const target = event.currentTarget;
            const { selectionStart, selectionEnd } = target;
            const next = `${code.slice(0, selectionStart)}    ${code.slice(selectionEnd)}`;
            setCode(next);
            requestAnimationFrame(() => target.setSelectionRange(selectionStart + 4, selectionStart + 4));
          }}
        />
      </label>
      <details className={styles.small}>
        <summary>The tests your code must pass</summary>
        <pre className={styles.code}>{problem.tests}</pre>
      </details>
      {state === "solved" ? (
        <p className={styles.passed} role="status">
          ✓ All tests pass. The module counts as passed.
        </p>
      ) : (
        <button
          type="button"
          className="button button--primary button--sm"
          disabled={state !== "idle"}
          onClick={() => void check()}
        >
          {state === "loading"
            ? "Loading Python… (the first time takes a moment)"
            : state === "running"
              ? "Running the tests…"
              : "Run the tests"}
        </button>
      )}
      {run && "error" in run && (
        <p className={styles.error} role="status">
          Not yet: {run.error}
        </p>
      )}
      {run?.output && <pre className={styles.code}>{run.output}</pre>}
      {error && <p className={styles.error}>{error}</p>}
      <p className={styles.small}>Your code runs in this browser only; it is not sent anywhere.</p>
    </div>
  );
}

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Something went wrong. Try again later.";
}
