// A capstone's end: the learner hands in their project as a link, an archive or both. A model reviews it
// against the capstone's rubric within a minute or so, with the evidence for each criterion; it is accepted or
// sent back with feedback. A person who reviews can see every review and decide otherwise.
import React, { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Download, ExternalLink, HelpCircle, Paperclip, X } from "lucide-react";
import { message, type PathApi } from "./api";
import {
  MAX_ARCHIVE_MB,
  progressOf,
  type PathItem,
  type ProjectReview,
  type ReviewedCriterion,
  type Submission,
} from "./model";
import { handleSignedOut, setPath } from "./store";
import { noteError } from "./pageErrors";
import { Spinner, StatusIcon } from "./ui";
import styles from "./path.module.css";

const POLL_MS = 4000;

export default function ProjectSubmission({ api, item }: { api: PathApi; item: PathItem }): ReactNode {
  const [submission, setSubmission] = useState<Submission | null | undefined>(undefined);
  const [editing, setEditing] = useState(false);
  const progress = progressOf(item);

  useEffect(() => {
    api
      .mySubmission(item.module.id)
      .then(setSubmission)
      .catch(() => setSubmission(null));
  }, [api, item.module.id, progress]);

  // While the model reads the project, ask for the result every few seconds; the path follows its decision.
  useEffect(() => {
    if (submission?.status !== "reviewing") return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api.mySubmission(item.module.id);
        if (next?.status !== "reviewing") {
          const session = await api.session();
          if (session.path) setPath(session.path);
        }
        setSubmission(next);
      } catch {
        setSubmission({ ...submission }); // try again at the next tick
      }
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [api, item.module.id, submission]);

  if (submission === undefined)
    return (
      <p className={styles.muted}>
        <Spinner /> Loading…
      </p>
    );

  const status = submission?.status;
  return (
    <div className={styles.project}>
      {status === "reviewing" && (
        <div className={styles.reviewing} role="status">
          <Spinner />
          <div>
            <strong>Reviewing your project…</strong>
            <p className={styles.muted}>
              An AI reviewer is reading your files and checking them against the rubric. This takes up to a minute;
              you can leave this page and come back.
            </p>
          </div>
        </div>
      )}
      {status === "submitted" && (
        <div className={styles.reviewing}>
          <StatusIcon status="submitted" />
          <div>
            <strong>Waiting for a reviewer</strong>
            <p className={styles.muted}>The automatic review is unavailable right now, so a person will look at it.</p>
          </div>
        </div>
      )}
      {(status === "accepted" || status === "returned") && submission && (
        <ReviewResult submission={submission} accepted={status === "accepted"} />
      )}
      {submission && <SubmissionCard api={api} submission={submission} />}
      {status === "submitted" && !editing && (
        <button type="button" className={styles.ghostSm} onClick={() => setEditing(true)}>
          Replace the submission
        </button>
      )}
      {(!submission || status === "returned" || editing) && progress !== "done" && (
        <SubmitForm
          api={api}
          item={item}
          previous={submission ?? null}
          onSubmitted={(next) => {
            setSubmission(next);
            setEditing(false);
          }}
        />
      )}
    </div>
  );
}

function ReviewResult({ submission, accepted }: { submission: Submission; accepted: boolean }): ReactNode {
  const review = submission.ai_review;
  const byPerson = submission.reviewed_by !== null && submission.reviewed_by !== "model";
  return (
    <div className={styles.result} data-passed={accepted}>
      <StatusIcon status={accepted ? "finished" : "returned"} />
      <div className={styles.resultBody}>
        <strong>
          {accepted
            ? `Your project passed${review?.level ? ` · level reached: ${review.level}` : ""}`
            : "Not passed yet: some criteria are missing"}
        </strong>
        <p>{submission.review_comment}</p>
        {byPerson && <p className={styles.muted}>Decided by a course reviewer.</p>}
        {review && <Rubric review={review} />}
      </div>
    </div>
  );
}

const VERDICT: Record<ReviewedCriterion["verdict"], string> = {
  met: "Met",
  not_met: "Not met",
  unverified: "Not shown",
};

function Rubric({ review }: { review: ProjectReview }): ReactNode {
  const [all, setAll] = useState(false);
  const levels = all ? review.levels : review.levels.filter((level) => level.passing);
  return (
    <div className={styles.rubric}>
      {levels.map((level) => (
        <div key={level.name}>
          <span className={styles.eyebrow}>
            {level.name}
            {level.passing && " · needed to pass"}
          </span>
          <ul>
            {level.criteria.map((criterion) => {
              const counts =
                criterion.verdict === "met" && !criterion.evidence_missing && !criterion.output_missing;
              return (
                <li key={criterion.name} data-counts={counts} data-verdict={criterion.verdict}>
                  <span className={styles.criterionMark} aria-hidden>
                    {counts ? <Check size={14} /> : criterion.verdict === "unverified" ? <HelpCircle size={14} /> : <X size={14} />}
                  </span>
                  <div>
                    <strong>{criterion.name}</strong>{" "}
                    <span className={styles.muted}>
                      {criterion.evidence_missing
                        ? "Not counted: the evidence is not in your files"
                        : criterion.output_missing
                          ? "Not counted: only your own words show it, not your program's output"
                          : VERDICT[criterion.verdict]}
                    </span>
                    <p>{criterion.comment}</p>
                    {counts && criterion.evidence.length > 0 && (
                      <p className={styles.evidence}>
                        {criterion.evidence.map((item) => (
                          <code key={`${item.file}${item.quote}`}>
                            {review.outputs.includes(item.file) && <span className={styles.outputTag}>output</span>}
                            {item.file}
                            {item.quote && `: ${item.quote.length > 80 ? `${item.quote.slice(0, 80)}…` : item.quote}`}
                          </code>
                        ))}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      <button type="button" className={styles.link} onClick={() => setAll(!all)}>
        {all ? "Show only what is needed to pass" : "Show the higher levels too"}
      </button>
      <p className={styles.fine}>
        Reviewed by AI from {review.files_read} of the {review.files_listed} files in your project. It does not run
        your code: how your project works counts only with what your code produced, such as notebook outputs or the
        logs and results it wrote.
      </p>
    </div>
  );
}

function SubmissionCard({ api, submission }: { api: PathApi; submission: Submission }): ReactNode {
  return (
    <div className={styles.submission}>
      <span className={styles.eyebrow}>Your submission · sent {new Date(submission.submitted_at).toLocaleDateString()}</span>
      {submission.link && (
        <a href={submission.link} target="_blank" rel="noopener noreferrer nofollow ugc">
          <ExternalLink size={15} aria-hidden /> {submission.link}
        </a>
      )}
      {submission.file_name && (
        <a href={api.archiveUrl(submission.id)} download>
          <Download size={15} aria-hidden /> {submission.file_name}
          {submission.file_size !== null && <span className={styles.muted}> · {size(submission.file_size)}</span>}
        </a>
      )}
      {submission.note && <p className={styles.muted}>{submission.note}</p>}
    </div>
  );
}

function SubmitForm({
  api,
  item,
  previous,
  onSubmitted,
}: {
  api: PathApi;
  item: PathItem;
  previous: Submission | null;
  onSubmitted: (submission: Submission) => void;
}): ReactNode {
  const [link, setLink] = useState(previous?.link ?? "");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  function choose(chosen: File | undefined) {
    setError(null);
    if (!chosen) return setFile(null);
    if (!/\.(zip|tar\.gz|tgz)$/i.test(chosen.name)) {
      setError(noted("Attach a .zip or a .tar.gz archive."));
      return setFile(null);
    }
    if (chosen.size > MAX_ARCHIVE_MB * 1024 * 1024) {
      setError(noted(`The archive is over ${MAX_ARCHIVE_MB} MB. Leave out data, models and dependencies, or give a link.`));
      return setFile(null);
    }
    setFile(chosen);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    if (link.trim()) form.append("link", link.trim());
    if (note.trim()) form.append("note", note.trim());
    if (file) form.append("archive", file);
    try {
      const sent = await api.submit(item.module.id, form);
      const session = await api.session();
      if (session.path) setPath(session.path);
      onSubmitted(sent);
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <p className={styles.muted}>
        An AI reviewer reads your code and checks it against the module's evaluation rubric above. Give the link to a
        public GitHub repository, attach an archive of the code, or both. It does not run your code, so include what
        your code produced: notebooks saved with their outputs, or the logs and result files it wrote, in folders
        such as <code>results/</code>, <code>outputs/</code> or <code>logs/</code>. Numbers you type into the README
        on their own do not count.
      </p>
      <label className={styles.field}>
        <span>Link to your project</span>
        <input
          type="url"
          inputMode="url"
          placeholder="https://github.com/you/project"
          maxLength={500}
          value={link}
          onChange={(event) => setLink(event.target.value)}
        />
      </label>
      <div className={styles.field}>
        <span>Archive (optional)</span>
        <div className={styles.fileRow}>
          <button type="button" className={styles.ghostSm} onClick={() => input.current?.click()}>
            <Paperclip size={15} aria-hidden /> {file ? "Choose another" : "Attach .zip or .tar.gz"}
          </button>
          <span className={styles.muted}>{file ? `${file.name} · ${size(file.size)}` : `Up to ${MAX_ARCHIVE_MB} MB`}</span>
          {file && (
            <button type="button" className={styles.link} onClick={() => choose(undefined)}>
              Remove
            </button>
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept=".zip,.tar.gz,.tgz,application/zip,application/gzip"
          hidden
          onChange={(event) => {
            choose(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>
      <label className={styles.field}>
        <span>Note (optional)</span>
        <textarea
          rows={3}
          maxLength={2000}
          placeholder="What you built, how to run it, what you would do next."
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.submitRow}>
        <span className={styles.fine}>You can submit 5 times a day. Your files go to the AI model's provider for the review; otherwise only you
          and the course reviewers see them.</span>
        <button type="submit" className={styles.primary} disabled={busy || (!link.trim() && !file)}>
          {busy && <Spinner />} {previous ? "Submit again" : "Submit for review"}
        </button>
      </div>
    </form>
  );
}

function size(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// A message the form shows without asking the server, kept for the assistant too.
function noted(text: string): string {
  noteError(text);
  return text;
}
