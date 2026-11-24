// For reviewers: the projects learners submitted, to accept or send back with a comment.
import React, { useEffect, useState, type ReactNode } from "react";
import useBaseUrl from "@docusaurus/useBaseUrl";
import { BarChart3, Download, ExternalLink } from "lucide-react";
import { message, usePathApi, type PathApi, type ReportedQuestion, type ReportReason } from "./api";
import { InlineMarkdown } from "./InlineMarkdown";
import type { Submission } from "./model";
import { Rubric } from "./ProjectSubmission";
import { openAuth, usePathState } from "./store";
import { useAnyModulePage } from "./useModulePages";
import { Spinner } from "./ui";
import styles from "./path.module.css";

export default function Review(): ReactNode {
  const api = usePathApi();
  const { ready, account } = usePathState();
  const [queue, setQueue] = useState<{ waiting: Submission[]; reviewed: Submission[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reportPage = useBaseUrl("/report");

  const load = () => {
    if (!api) return;
    api
      .reviewQueue()
      .then(setQueue)
      .catch((reason: unknown) => setError(message(reason)));
  };
  useEffect(load, [api, account?.email]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!api || !ready)
    return (
      <p className={styles.muted}>
        <Spinner /> Loading…
      </p>
    );
  if (!account)
    return (
      <div className={styles.card}>
        <p>Sign in with a reviewer account to see submitted projects.</p>
        <button type="button" className={styles.primary} onClick={() => openAuth("sign-in")}>
          Sign in
        </button>
      </div>
    );
  if (!account.reviewer) return <p className={styles.error}>This account is not a reviewer.</p>;

  return (
    <div className={styles.ppRoot}>
      <div className={styles.pathPage}>
        <header>
          <span className={styles.eyebrow}>Reviews</span>
          <h1>Submitted projects</h1>
          <p className={styles.muted}>
            An AI reviewer grades every project against its rubric as soon as it is submitted. Here you see its
            decisions, criterion by criterion, and can change them. Open archives on a machine you trust: they are
            learners' code.
          </p>
          <p>
            <a href={reportPage}>
              <BarChart3 size={15} aria-hidden /> Where learners stop
            </a>
          </p>
        </header>
        {error && <p className={styles.error}>{error}</p>}
        {!queue ? (
          <p className={styles.muted}>
            <Spinner /> Loading…
          </p>
        ) : (
          <>
            {/* Only submissions from before every project went to the AI reviewer can still wait for a person. */}
            {queue.waiting.length > 0 && (
              <section className={styles.section}>
                <h2>
                  Waiting for a person <span className={styles.muted}>{queue.waiting.length}</span>
                </h2>
                <ul className={styles.reviewList}>
                  {queue.waiting.map((submission) => (
                    <ReviewItem key={submission.id} api={api} submission={submission} onDone={load} />
                  ))}
                </ul>
              </section>
            )}
            {queue.reviewed.length === 0 ? (
              <p className={styles.muted}>No project has been submitted yet.</p>
            ) : (
              <section className={styles.section}>
                <h2>Decided recently</h2>
                <ul className={styles.reviewList}>
                  {queue.reviewed.map((submission) => (
                    <ReviewItem key={submission.id} api={api} submission={submission} onDone={load} />
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
        <QuestionReports api={api} />
      </div>
    </div>
  );
}

const REASON_LABEL: Record<ReportReason, string> = {
  wrong_answer: "The answer key is wrong",
  unclear: "Unclear question or options",
  off_topic: "The module does not teach this",
  wrong_mark: "An open answer marked wrong",
  other: "Something else",
};
const LETTERS = ["A", "B", "C", "D"];

// Checkpoint questions learners reported. The fix itself goes into the checkpoint's file in the repository;
// here a reviewer reads the report next to the question and marks it resolved.
function QuestionReports({ api }: { api: PathApi }): ReactNode {
  const [reports, setReports] = useState<ReportedQuestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => {
    api
      .questionReports()
      .then(setReports)
      .catch((reason: unknown) => setError(message(reason)));
  };
  useEffect(load, [api]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = reports?.filter((report) => !report.resolved) ?? [];
  return (
    <section className={styles.section}>
      <h2>
        Reported questions <span className={styles.muted}>{reports ? open.length : ""}</span>
      </h2>
      <p className={styles.muted}>
        Learners flag checkpoint questions that look wrong. Take a wrong question out of its checkpoint at once:
        learners stop getting it, and the topic's other questions take its place. Fix it in the checkpoint's file
        and put it back later, or mark a report resolved when the question is right.
      </p>
      {error && <p className={styles.error}>{error}</p>}
      {!reports ? (
        <p className={styles.muted}>
          <Spinner /> Loading…
        </p>
      ) : reports.length === 0 ? (
        <p className={styles.muted}>No question has been reported.</p>
      ) : (
        <ul className={styles.reviewList}>
          {reports.map((report) => (
            <li key={report.id} className={styles.card} data-resolved={report.resolved}>
              <p className={styles.muted}>
                {report.module_title} · question {report.question_id} ·{" "}
                {new Date(report.reported_at).toLocaleDateString()}
                {report.retired ? " · taken out of the checkpoint" : report.resolved && " · resolved"}
              </p>
              <p>
                <strong>{REASON_LABEL[report.reason]}</strong>
                {report.comment && <>: “{report.comment}”</>}
              </p>
              {report.question ? (
                <>
                  <p>
                    <InlineMarkdown text={report.question.text} />
                  </p>
                  <ol className={styles.reportOptions}>
                    {report.question.options.map((option, index) => (
                      <li key={index} data-answer={index === report.question!.answer}>
                        <span>{LETTERS[index]}</span> <InlineMarkdown text={option} />
                        {index === report.question!.answer && <em> (answer key)</em>}
                      </li>
                    ))}
                  </ol>
                  <p className={styles.muted}>
                    <InlineMarkdown text={report.question.explanation} />
                  </p>
                </>
              ) : report.open_question ? (
                <>
                  <p>
                    <InlineMarkdown text={report.open_question.text} />
                  </p>
                  <p className={styles.muted}>
                    Open question: right with {report.open_question.required} of these points.
                  </p>
                  <ol className={styles.reportOptions}>
                    {report.open_question.rubric.map((point, index) => (
                      <li key={index}>
                        <InlineMarkdown text={point} />
                      </li>
                    ))}
                  </ol>
                  <p className={styles.muted}>
                    <InlineMarkdown text={report.open_question.model_answer} />
                  </p>
                </>
              ) : (
                <p className={styles.muted}>The checkpoint no longer has this question.</p>
              )}
              <div className={styles.actions}>
                {(report.question || report.open_question) && (
                  <button
                    type="button"
                    className={report.retired ? styles.ghostSm : styles.primarySm}
                    onClick={() =>
                      void api
                        .retireQuestion(report.id, !report.retired)
                        .then(load)
                        .catch((reason: unknown) => setError(message(reason)))
                    }
                  >
                    {report.retired ? "Put it back in the checkpoint" : "Take it out of the checkpoint"}
                  </button>
                )}
                {!report.retired && (
                  <button
                    type="button"
                    className={styles.ghostSm}
                    onClick={() =>
                      void api
                        .resolveQuestionReport(report.id, !report.resolved)
                        .then(load)
                        .catch((reason: unknown) => setError(message(reason)))
                    }
                  >
                    {report.resolved ? "Open again" : "Mark resolved: the question is right"}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ReviewItem({
  api,
  submission,
  onDone,
}: {
  api: PathApi;
  submission: Submission;
  onDone: () => void;
}): ReactNode {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const page = useAnyModulePage()(submission.module_id);
  const review = submission.ai_review;

  async function decide(accept: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api.review(submission.id, accept, comment.trim());
      onDone();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`${styles.card} ${styles.reviewItem}`}>
      <div className={styles.reviewHead}>
        {page ? (
          <a href={page}>
            <strong>{submission.module_title}</strong>
          </a>
        ) : (
          <strong>{submission.module_title}</strong>
        )}
        <span className={styles.muted}>
          {submission.email} · {new Date(submission.submitted_at).toLocaleString()}
        </span>
      </div>
      {submission.status !== "submitted" && (
        <p className={submission.status === "accepted" ? styles.success : styles.muted}>
          {submission.status === "accepted" ? "Accepted" : "Sent back"} by{" "}
          {submission.reviewed_by === "model" ? "the AI reviewer" : submission.reviewed_by}
          {review?.level && ` · level reached: ${review.level}`}
        </p>
      )}
      {submission.review_comment && <p>{submission.review_comment}</p>}
      {review && review.levels.some((level) => level.criteria.length > 0) && (
        <details className={styles.reviewDetails}>
          <summary>The AI's review, criterion by criterion</summary>
          <Rubric review={review} forReviewer />
        </details>
      )}
      <div className={styles.submission}>
        {submission.link && (
          <a href={submission.link} target="_blank" rel="noopener noreferrer nofollow ugc">
            <ExternalLink size={15} aria-hidden /> {submission.link}
          </a>
        )}
        {submission.file_name && (
          <a href={api.archiveUrl(submission.id)} download>
            <Download size={15} aria-hidden /> {submission.file_name}
          </a>
        )}
        {submission.note && <p>{submission.note}</p>}
      </div>
      <label className={styles.field}>
        <span>{submission.status === "submitted" ? "Comment for the learner" : "Change the decision: comment"}</span>
        <textarea
          rows={2}
          maxLength={2000}
          value={comment}
          placeholder="Required when you send the project back."
          onChange={(event) => setComment(event.target.value)}
        />
      </label>
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.actions}>
        <button type="button" className={styles.primarySm} disabled={busy} onClick={() => void decide(true)}>
          Accept
        </button>
        <button
          type="button"
          className={styles.ghostSm}
          disabled={busy || !comment.trim()}
          onClick={() => void decide(false)}
        >
          Send back for changes
        </button>
      </div>
    </li>
  );
}
