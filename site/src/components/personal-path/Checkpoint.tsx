import React, { useEffect, useState, type ReactNode } from "react";
import { ApiError, type PathApi } from "./api";
import type { CheckpointQuestions, Grade, LearningPath } from "./model";
import { InlineMarkdown } from "./InlineMarkdown";
import styles from "./PersonalPath.module.css";

// One attempt at a module's checkpoint. The API grades it and returns the path with the result.
export default function Checkpoint({
  api,
  path,
  moduleId,
  attempt,
  onResult,
}: {
  api: PathApi;
  path: LearningPath;
  moduleId: string;
  attempt: number;
  onResult: (path: LearningPath) => void;
}): ReactNode {
  const [asked, setAsked] = useState<CheckpointQuestions | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [grade, setGrade] = useState<Grade | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setAsked(null);
    setAnswers({});
    setGrade(null);
    api
      .checkpoint(moduleId, attempt, path.curriculum_version)
      .then(setAsked)
      .catch((reason: unknown) => setError(message(reason)));
  }, [api, moduleId, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.attempt(path, moduleId, attempt, answers);
      setGrade(result.grade);
      onResult(result.path);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className={styles.error}>{error}</p>;
  if (!asked) return <p className={styles.small}>Loading the checkpoint…</p>;

  const feedback = new Map(grade?.feedback.map((item) => [item.id, item]));
  const complete = asked.questions.every((question) => question.id in answers);

  return (
    <form
      className={styles.checkpoint}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className={styles.small}>
        {asked.questions.length} questions; {asked.pass_mark} right answers pass.
        {asked.status === "draft" && " These questions are a draft and have not been reviewed yet."}
      </p>
      {asked.questions.map((question, number) => {
        const result = feedback.get(question.id);
        return (
          <fieldset key={question.id} className={styles.question} data-correct={result?.correct}>
            <legend>
              {number + 1}. <InlineMarkdown text={question.text} />
            </legend>
            {question.options.map((option, index) => (
              <label key={index} className={styles.option}>
                <input
                  type="radio"
                  name={question.id}
                  disabled={grade !== null}
                  checked={answers[question.id] === index}
                  onChange={() => setAnswers({ ...answers, [question.id]: index })}
                />{" "}
                <InlineMarkdown text={option} />
                {result?.answer === index && " ✓"}
              </label>
            ))}
            {result && (
              <p className={styles.small}>
                {result.correct ? "Right." : "Not quite."}{" "}
                {result.explanation && <InlineMarkdown text={result.explanation} />}
              </p>
            )}
          </fieldset>
        );
      })}
      {grade ? (
        <p className={grade.passed ? styles.passed : styles.error} role="status">
          {grade.score} of {grade.total} right.{" "}
          {grade.passed
            ? grade.effortless
              ? "Passed without a mistake. Your path may suggest lightening what comes next."
              : "Passed."
            : "Not passed yet: the modules after this one stay locked until you pass. The right answers are shown once you pass; next time you get other questions."}
          {grade.passed && grade.problem_pending && " One coding problem is left below."}
        </p>
      ) : (
        <button type="submit" className="button button--primary" disabled={!complete || busy}>
          {busy ? "Checking…" : "Check my answers"}
        </button>
      )}
      {grade && !grade.passed && grade.review_topics.length > 0 && (
        <div className={styles.small}>
          Review before your next attempt:
          <ul>
            {grade.review_topics.map((topic) => (
              <li key={topic}>{topic}</li>
            ))}
          </ul>
        </div>
      )}
    </form>
  );
}

function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Something went wrong. Try again later.";
}
