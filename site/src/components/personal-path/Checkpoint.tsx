// One attempt at a module's checkpoint. The API grades it against the learner's stored path and returns the
// path with the result. An open question, answered in the learner's own words, is marked by a model against
// the points a full answer makes.
import React, { useEffect, useState, type ReactNode } from "react";
import clsx from "clsx";
import { Check, Flag, X } from "lucide-react";
import { message, type PathApi, type ReportReason } from "./api";
import { topicsToReview, type CheckpointQuestions, type Grade, type LearningPath } from "./model";
import { InlineMarkdown } from "./InlineMarkdown";
import { handleSignedOut, setPath } from "./store";
import { ReviewTopics, Spinner } from "./ui";
import styles from "./path.module.css";

const LETTERS = ["A", "B", "C", "D"];

export default function Checkpoint({
  api,
  path,
  moduleId,
  attempt,
  onRetake,
}: {
  api: PathApi;
  path: LearningPath;
  moduleId: string;
  attempt: number;
  onRetake?: () => void;
}): ReactNode {
  const [asked, setAsked] = useState<CheckpointQuestions | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [openAnswers, setOpenAnswers] = useState<Record<string, string>>({});
  const [grade, setGrade] = useState<Grade | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .checkpoint(moduleId, attempt, path.curriculum_version)
      .then(setAsked)
      .catch((reason: unknown) => setError(message(reason)));
  }, [api, moduleId, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.attempt(moduleId, attempt, answers, openAnswers);
      setGrade(result.grade);
      setPath(result.path);
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  if (!asked)
    return error ? (
      <p className={styles.error}>{error}</p>
    ) : (
      <p className={styles.muted}>
        <Spinner /> Loading the questions…
      </p>
    );

  const feedback = new Map(grade?.feedback.map((item) => [item.id, item]));
  const item = path.items.find((candidate) => candidate.module.id === moduleId);
  const answered = asked.questions.filter((question) =>
    question.kind === "open" ? (openAnswers[question.id] ?? "").trim() !== "" : question.id in answers,
  ).length;
  const hasOpen = asked.questions.some((question) => question.kind === "open");

  return (
    <form
      className={styles.quiz}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {asked.questions.map((question, number) => {
        const result = feedback.get(question.id);
        return (
          <fieldset
            key={question.id}
            className={styles.quizQuestion}
            data-result={result ? (result.correct ? "right" : "wrong") : undefined}
          >
            <legend>
              <span className={styles.quizNumber}>{number + 1}</span>
              <span>
                <InlineMarkdown text={question.text} />
              </span>
            </legend>
            {question.kind === "open" ? (
              <OpenAnswer
                value={openAnswers[question.id] ?? ""}
                disabled={grade !== null}
                onChange={(text) => setOpenAnswers({ ...openAnswers, [question.id]: text })}
              />
            ) : (
              <div className={styles.options}>
                {question.options.map((option, index) => {
                  const chosen = answers[question.id] === index;
                  const right = result?.answer === index;
                  return (
                    <label
                      key={index}
                      className={clsx(styles.option, {
                        [styles.optionChosen]: chosen,
                        [styles.optionRight]: right,
                        [styles.optionWrong]: result && chosen && !result.correct,
                      })}
                    >
                      <input
                        type="radio"
                        name={question.id}
                        disabled={grade !== null}
                        checked={chosen}
                        onChange={() => setAnswers({ ...answers, [question.id]: index })}
                      />
                      <span className={styles.optionLetter}>{LETTERS[index]}</span>
                      <span>
                        <InlineMarkdown text={option} />
                      </span>
                      {right && <Check size={16} className={styles.optionMark} aria-label="Right answer" />}
                      {result && chosen && !result.correct && (
                        <X size={16} className={styles.optionMark} aria-label="Your answer, not right" />
                      )}
                    </label>
                  );
                })}
              </div>
            )}
            {result?.comment && (
              <p className={styles.explanation}>
                <InlineMarkdown text={result.comment} />
              </p>
            )}
            {result?.explanation && (
              <p className={styles.explanation}>
                {result.kind === "open" && <strong>A full answer: </strong>}
                <InlineMarkdown text={result.explanation} />
              </p>
            )}
            {result && !result.correct && result.graded !== false && !result.explanation && (
              <p className={styles.explanation}>
                {result.kind === "open"
                  ? "Not enough for this one. A full answer is shown once you pass."
                  : "Not right. The answer is shown once you pass."}
              </p>
            )}
            <ReportQuestion
              api={api}
              moduleId={moduleId}
              questionId={question.id}
              openAnswer={result && result.kind === "open" && !result.correct ? openAnswers[question.id] : undefined}
            />
          </fieldset>
        );
      })}

      {grade ? (
        <div className={styles.result} data-passed={grade.passed} role="status">
          <span className={styles.score}>
            {grade.score}/{grade.total}
          </span>
          <div>
            <strong>
              {grade.passed
                ? grade.effortless
                  ? "Passed without a mistake"
                  : "Passed"
                : "Not passed yet"}
            </strong>
            <p>
              {grade.passed
                ? grade.problem_pending
                  ? "One short coding problem is left, below."
                  : grade.effortless
                    ? "Your path may suggest lightening the modules that build on this one."
                    : "The module counts as completed."
                : `You need ${asked.pass_mark} right. The modules after this one stay locked until you pass; the next attempt has other questions.`}
            </p>
            {!grade.passed && item && (
              <ReviewTopics topics={topicsToReview({ ...item, missed_topics: grade.review_topics })} />
            )}
            {!grade.passed && onRetake && (
              <button type="button" className={styles.primarySm} onClick={onRetake}>
                Try again
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className={styles.submitRow}>
          <span className={styles.muted}>
            {answered} of {asked.questions.length} answered
          </span>
          <button
            type="submit"
            className={styles.primary}
            disabled={answered < asked.questions.length || busy}
          >
            {busy && <Spinner />} {busy && hasOpen ? "Checking your answers…" : "Check my answers"}
          </button>
        </div>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </form>
  );
}

const REASONS: { value: ReportReason; label: string }[] = [
  { value: "wrong_answer", label: "The answer counted as right is wrong" },
  { value: "unclear", label: "The question or the options are unclear" },
  { value: "off_topic", label: "The module does not teach this" },
  { value: "other", label: "Something else" },
];

const MARK_REASON: { value: ReportReason; label: string } = {
  value: "wrong_mark",
  label: "My answer is right but was marked as not enough",
};

// The answer box of an open question.
function OpenAnswer({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (text: string) => void;
}): ReactNode {
  return (
    <div className={styles.openAnswer}>
      <textarea
        rows={5}
        maxLength={2000}
        disabled={disabled}
        value={value}
        aria-label="Your answer"
        placeholder="Explain in your own words, in two to five sentences."
        onChange={(event) => onChange(event.target.value)}
      />
      <span className={styles.reportNote}>
        A model checks your answer for the points a full answer makes; wording and English do not count.
      </span>
    </div>
  );
}

// "Report this question": a learner who meets a wrong or unclear question says so, and a reviewer checks it.
// It does not change the learner's score.
function ReportQuestion({
  api,
  moduleId,
  questionId,
  openAnswer,
}: {
  api: PathApi;
  moduleId: string;
  questionId: string;
  openAnswer?: string; // an open answer marked not enough: the learner may dispute the mark
}): ReactNode {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  if (state === "sent")
    return <p className={styles.reportDone}>Thanks, a reviewer will check this question.</p>;
  if (!open)
    return (
      <button type="button" className={styles.reportLink} onClick={() => setOpen(true)}>
        <Flag size={13} aria-hidden /> Report this question
      </button>
    );

  async function send() {
    if (!reason) return;
    setState("sending");
    setError(null);
    try {
      // A disputed mark carries the answer, so the reviewer sees what was marked.
      const sent =
        reason === "wrong_mark" && openAnswer
          ? `${comment ? `${comment}\n\n` : ""}My answer: ${openAnswer}`.slice(0, 1000)
          : comment;
      await api.reportQuestion(moduleId, questionId, reason, sent);
      setState("sent");
    } catch (failure) {
      if (!handleSignedOut(failure)) setError(message(failure));
      setState("idle");
    }
  }

  return (
    <div className={styles.reportBox} role="group" aria-label="Report this question">
      <strong>What is wrong with this question?</strong>
      {(openAnswer ? [MARK_REASON, ...REASONS] : REASONS).map((option) => (
        <label key={option.value} className={styles.reportReason}>
          <input
            type="radio"
            name={`report-${questionId}`}
            checked={reason === option.value}
            onChange={() => setReason(option.value)}
          />
          {option.label}
        </label>
      ))}
      <textarea
        rows={2}
        maxLength={1000}
        value={comment}
        aria-label="Details, if you like"
        placeholder="Details, if you like"
        onChange={(event) => setComment(event.target.value)}
      />
      <span className={styles.reportNote}>A report does not change your score.</span>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primarySm}
          disabled={!reason || state === "sending"}
          onClick={() => void send()}
        >
          {state === "sending" && <Spinner />} Send report
        </button>
        <button type="button" className={styles.ghostSm} onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
