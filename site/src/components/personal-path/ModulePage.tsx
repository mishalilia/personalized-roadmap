// What the learner's path says on a module's own page: a short panel above the content (the decision, why,
// where the module stands), and the checkpoint below it, where the learner finishes the module and moves
// on to the next one in their path.
import React, { useState, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import { useDoc, useDocsVersion } from "@docusaurus/plugin-content-docs/client";
import { ArrowDown, ArrowRight, Lock, Sparkles } from "lucide-react";
import { message, usePathApi, type PassedQuestion, type PathApi } from "./api";
import Checkpoint from "./Checkpoint";
import CodingProblem from "./CodingProblem";
import { InlineMarkdown } from "./InlineMarkdown";
import ProjectSubmission from "./ProjectSubmission";
import ModuleTopics from "./ModuleTopics";
import {
  isLocked,
  nextAfter,
  progressOf,
  proposalAction,
  statusOf,
  stepOf,
  topicsToReview,
  type Choice,
  type LearningPath,
  type PathItem,
  CHECKPOINT_ANCHOR,
} from "./model";
import {
  handleSignedOut,
  openAuth,
  setDrawer,
  setPath,
  showConfirmation,
  useCheckpoints,
  usePathState,
} from "./store";
import { changePath, withChoice } from "./changes";
import { useModulePages, useVersionLabel } from "./useModulePages";
import { ChoiceChip, ReviewTopics, STATUS_LABEL, Spinner, StatusIcon } from "./ui";
import styles from "./path.module.css";


// The learner's path and this page's module in it, if the path covers this version of the page.
function useModuleOfPage(): {
  path: LearningPath | null;
  item: PathItem | undefined;
  otherVersion: boolean;
} {
  const { metadata } = useDoc();
  const version = useDocsVersion();
  const { path } = usePathState();
  const item = path?.items.find((candidate) => candidate.module.id === metadata.id);
  if (!path || !item) return { path: null, item: undefined, otherVersion: false };
  const matches = (path.curriculum_site_version ?? null) === version.version;
  return { path: matches ? path : null, item: matches ? item : undefined, otherVersion: !matches };
}

async function change(action: () => Promise<LearningPath>, onError: (text: string) => void) {
  try {
    setPath(await action());
  } catch (reason) {
    if (!handleSignedOut(reason)) onError(message(reason));
  }
}

export function ModulePanel(): ReactNode {
  const api = usePathApi();
  const { account, path: anyPath } = usePathState();
  const { path, item, otherVersion } = useModuleOfPage();
  const pageOf = useModulePages(anyPath?.curriculum_site_version ?? null);
  const versionLabel = useVersionLabel(anyPath?.curriculum_site_version ?? null);
  const checkpoints = useCheckpoints(api, path?.curriculum_version);
  const [error, setError] = useState<string | null>(null);
  const { metadata } = useDoc();

  if (otherVersion) {
    const page = pageOf(metadata.id);
    return page ? (
      <aside className={styles.panel} data-tone="muted">
        <p>
          Your path covers this module in the <strong>{versionLabel ?? "other"}</strong> curriculum.{" "}
          <Link to={page}>Open that version</Link> to work on it.
        </p>
      </aside>
    ) : null;
  }
  if (!api || !path || !item) return null;

  const status = statusOf(path, item);
  const step = stepOf(path, item.module.id);
  const hasCheckpoint = item.module.id in checkpoints;
  const proposals = path.proposals?.filter((p) => p.module_id === item.module.id) ?? [];
  const blocking = path.items.find((i) => i.module.id === path.blocking_module_id);
  const signedIn = account !== null;

  // A decision made on the module page is the learner's own approval, so a confirmed path stays confirmed.
  // Changing a module on its page is the learner's own approval: a confirmed path stays confirmed.
  function choose(choice: Choice) {
    if (!signedIn) return openAuth("sign-up", "Create an account to change and keep your path.");
    if (choice === item!.choice) return;
    const confirmed = Boolean(path!.confirmed_at);
    changePath(
      api!,
      (current) => withChoice(current, item!.module.id, choice, confirmed),
      async () => {
        const changed = await api!.choose(item!.module.id, choice);
        return confirmed ? api!.confirm() : changed;
      },
      setError,
    );
  }

  return (
    <aside className={styles.panel} data-choice={item.choice} aria-label="Your personal path">
      <div className={styles.panelHead}>
        <ChoiceChip choice={item.choice} />
        <span className={styles.panelTitle}>
          {item.choice === "skip"
            ? "Your path skips this module"
            : item.choice === "prove"
              ? "Prove you know this module"
              : "Study this module"}
        </span>
        {step && item.choice !== "skip" && (
          <span className={styles.muted}>
            Module {step.step} of {step.total} in your path
          </span>
        )}
        {path.confirmed_at && item.choice !== "skip" && (
          <span className={styles.panelStatus} data-status={status}>
            <StatusIcon status={status} size={16} /> {statusText(item, status)}
          </span>
        )}
      </div>

      <p className={styles.reason}>{explanation(item)}</p>
      {status === "failed" && <ReviewTopics topics={topicsToReview(item)} lead="Review before the next try" />}
      <ModuleTopics item={item} hasCheckpoint={hasCheckpoint} passed={status === "finished"} />

      {status === "locked" && blocking && (
        <p className={styles.lockNote}>
          <Lock size={15} aria-hidden /> Locked until you pass the checkpoint of{" "}
          {pageOf(blocking.module.id) ? (
            <Link to={pageOf(blocking.module.id)!}>{blocking.module.title}</Link>
          ) : (
            blocking.module.title
          )}
          .
        </p>
      )}

      {proposals.map((proposal) => (
        <div key={proposal.topic ?? ""} className={styles.proposal}>
          <Sparkles size={16} aria-hidden />
          <span>
            After your last checkpoint, your path suggests to <strong>{proposalAction(proposal)}</strong>.{" "}
            {proposal.reason}
          </span>
          <span className={styles.actions}>
            <button
              type="button"
              className={styles.primarySm}
              onClick={() => void change(() => api.act("accept", item.module.id, proposal.topic), setError)}
            >
              Accept
            </button>
            <button
              type="button"
              className={styles.ghostSm}
              onClick={() => void change(() => api.act("decline", item.module.id, proposal.topic), setError)}
            >
              Keep as is
            </button>
          </span>
        </div>
      ))}

      <div className={styles.actions}>
        {!signedIn ? (
          <>
            <button type="button" className={styles.primarySm} onClick={() => openAuth("sign-up")}>
              Save my path
            </button>
            <span className={styles.muted}>Create a free account to track your progress.</span>
          </>
        ) : !path.confirmed_at ? (
          <button type="button" className={styles.primarySm} onClick={showConfirmation}>
            Review and confirm your path
          </button>
        ) : item.choice === "skip" ? (
          <button type="button" className={styles.ghostSm} onClick={() => choose("study")}>
            Add it to my path
          </button>
        ) : (
          status !== "locked" &&
          status !== "finished" && (
            <a href={`#${CHECKPOINT_ANCHOR}`} className={styles.ghostSm}>
              {item.module.is_project
                ? "Submit your project"
                : hasCheckpoint
                  ? "Go to the checkpoint"
                  : "Finish the module"} <ArrowDown size={14} aria-hidden />
            </a>
          )
        )}
      </div>
      {error && <p className={styles.error}>{error}</p>}
    </aside>
  );
}

function statusText(item: PathItem, status: ReturnType<typeof statusOf>): string {
  if (status === "finished") return item.last_score ? `Passed (${item.last_score})` : "Completed";
  if (status === "failed") return `Not passed yet (${item.last_score})`;
  return STATUS_LABEL[status];
}

function explanation(item: PathItem): string {
  if (item.adjustment) return item.adjustment;
  if (item.choice !== item.suggested)
    return `You chose this yourself; your path suggested to ${item.suggested} it: ${item.reason}`;
  return item.reason;
}

// Below the module's content: its checkpoint, or marking it done, and the way to the next module.
export function ModuleFinish(): ReactNode {
  const api = usePathApi();
  const { account } = usePathState();
  const { path, item } = useModuleOfPage();
  const checkpoints = useCheckpoints(api, path?.curriculum_version);
  const pageOf = useModulePages(path?.curriculum_site_version ?? null);

  if (!api) return null;
  if (!path || !item || !account || !path.confirmed_at) return <CheckpointWaiting />;
  if (item.choice === "skip" || isLocked(path, item.module.id)) return null;

  const next = nextAfter(path, item.module.id);
  const nextHref = next && pageOf(next.module.id);
  const summary = checkpoints[item.module.id];

  return (
    <section id={CHECKPOINT_ANCHOR} className={styles.finish} aria-label="Finish this module">
      <div className={styles.finishHead}>
        <span className={styles.eyebrow}>Your path</span>
        <h2>{item.module.is_project ? "Submit your project" : summary ? "Checkpoint" : "Finish this module"}</h2>
        {summary && (
          <p className={styles.muted}>
            {summary.questions_per_attempt} questions; {summary.pass_mark} right answers pass
            {summary.has_problem && ", then one short coding problem"}.
            {item.choice === "prove" && " Pass it to prove the module without studying it."}
          </p>
        )}
      </div>
      {item.module.is_project ? (
        <ProjectSubmission api={api} item={item} />
      ) : summary ? (
        <CheckpointFlow api={api} path={path} item={item} hasProblem={summary.has_problem} />
      ) : (
        <MarkDone api={api} item={item} />
      )}
      {next && nextHref && !isLocked(path, next.module.id) && (
        <Link to={nextHref} className={styles.nextCard}>
          <span>
            <span className={styles.muted}>Next in your path</span>
            <strong>{next.module.title}</strong>
          </span>
          <ChoiceChip choice={next.choice} />
          <ArrowRight size={18} aria-hidden />
        </Link>
      )}
      {next && isLocked(path, next.module.id) && (
        <p className={styles.lockNote}>
          <Lock size={15} aria-hidden /> Next in your path: {next.module.title}, once you pass this checkpoint.
        </p>
      )}
    </section>
  );
}

// A module with a checkpoint, seen before the learner can take it: say what opens it, instead of showing
// nothing where the checkpoint will be.
function CheckpointWaiting(): ReactNode {
  const api = usePathApi();
  const { account, path: anyPath } = usePathState();
  const { metadata } = useDoc();
  const version = useDocsVersion();
  const checkpoints = useCheckpoints(api, version.version);
  const summary = checkpoints[metadata.id];
  // A path for another version of the course is handled by the panel above the content.
  if (!summary || (anyPath && (anyPath.curriculum_site_version ?? null) !== version.version)) return null;

  const [text, action, onClick] = !anyPath
    ? [
        "Get a personal path first: a few questions about you, then this checkpoint opens here.",
        "Get my path",
        () => setDrawer(true),
      ]
    : !account
      ? [
          "Create a free account to keep your path; the checkpoint opens once your path is saved and confirmed.",
          "Create an account",
          () => openAuth("sign-up", "Create an account to take checkpoints and keep your progress."),
        ]
      : [
          "Confirm your path to open this checkpoint: review what to study, prove or skip, then confirm.",
          "Review and confirm my path",
          showConfirmation,
        ];

  return (
    <section id={CHECKPOINT_ANCHOR} className={styles.finish} aria-label="Checkpoint">
      <div className={styles.finishHead}>
        <span className={styles.eyebrow}>Your path</span>
        <h2>Checkpoint</h2>
        <p className={styles.muted}>
          {summary.questions_per_attempt} questions; {summary.pass_mark} right answers pass
          {summary.has_problem && ", then one short coding problem"}.
        </p>
      </div>
      <div className={styles.startRow}>
        <span className={styles.muted}>{text}</span>
        <button type="button" className={styles.primary} onClick={onClick}>
          {action}
        </button>
      </div>
    </section>
  );
}

function CheckpointFlow({
  api,
  path,
  item,
  hasProblem,
}: {
  api: PathApi;
  path: LearningPath;
  item: PathItem;
  hasProblem: boolean;
}): ReactNode {
  // The attempt on screen; it stays with its result until the learner starts another.
  const [taking, setTaking] = useState<number | null>(null);
  const progress = progressOf(item);
  // The coding problem stays on screen, with its result, once the module turns "passed".
  const [problemShown, setProblemShown] = useState(progress === "practice");
  if (progress === "practice" && !problemShown) setProblemShown(true);
  // After the module is passed, the problem can be opened again to practise; solving it then records nothing.
  const [practising, setPractising] = useState(false);

  return (
    <>
      {taking !== null ? (
        <Checkpoint
          key={taking}
          api={api}
          path={path}
          moduleId={item.module.id}
          attempt={taking}
          onRetake={progressOf(item) === "failed" ? () => setTaking(item.attempts ?? 0) : undefined}
        />
      ) : progress === "passed" ? (
        <p className={styles.success}>
          <StatusIcon status="finished" /> You passed this checkpoint ({item.last_score}).
        </p>
      ) : (
        progress !== "practice" && (
          <div className={styles.startRow}>
            {progress === "failed" && (
              <span className={styles.muted}>
                Last attempt: {item.last_score}. Review the topics, then try again — you will get other
                questions.
                <ReviewTopics topics={topicsToReview(item)} />
              </span>
            )}
            <button type="button" className={styles.primary} onClick={() => setTaking(item.attempts ?? 0)}>
              {progress === "failed" ? "Try again" : "Start the checkpoint"}
            </button>
          </div>
        )
      )}
      {taking === null && (progress === "practice" || progress === "passed") && (
        <PassedQuestions api={api} moduleId={item.module.id} />
      )}
      {problemShown && <CodingProblem api={api} path={path} moduleId={item.module.id} />}
      {!problemShown && progress === "passed" && hasProblem && taking === null &&
        (practising ? (
          <CodingProblem api={api} path={path} moduleId={item.module.id} practice />
        ) : (
          <button type="button" className={styles.ghostSm} onClick={() => setPractising(true)}>
            Solve the coding problem again
          </button>
        ))}
    </>
  );
}

function MarkDone({ api, item }: { api: PathApi; item: PathItem }): ReactNode {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (progressOf(item) === "done")
    return (
      <p className={styles.success}>
        <StatusIcon status="finished" /> You marked this module as done.
      </p>
    );
  return (
    <div className={styles.startRow}>
      <span className={styles.muted}>This module has no checkpoint. Mark it done when you have worked through it.</span>
      <button
        type="button"
        className={styles.primary}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await change(() => api.act("done", item.module.id), setError);
          setBusy(false);
        }}
      >
        {busy && <Spinner />} Mark as done
      </button>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}

// The questions of the attempt the learner passed, with the right answers, folded until asked for: to look
// back at while solving the coding problem, or later.
function PassedQuestions({ api, moduleId }: { api: PathApi; moduleId: string }): ReactNode {
  const [questions, setQuestions] = useState<PassedQuestion[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!open && !questions) {
      try {
        setQuestions(await api.passedQuestions(moduleId));
      } catch (reason) {
        if (!handleSignedOut(reason)) setError(message(reason));
        return;
      }
    }
    setOpen(!open);
  }

  return (
    <div className={styles.passedQuestions}>
      <button type="button" className={styles.ghostSm} onClick={() => void toggle()} aria-expanded={open}>
        {open ? "Hide the checkpoint questions" : "Review the checkpoint questions"}
      </button>
      {error && <p className={styles.error}>{error}</p>}
      {open && questions && (
        <ol className={styles.passedList}>
          {questions.map((question) => (
            <li key={question.id}>
              <InlineMarkdown text={question.text} />
              {question.options.length > 0 && (
                <ul>
                  {question.options.map((option, index) => (
                    <li key={index} data-right={index === question.answer}>
                      <InlineMarkdown text={option} />
                    </li>
                  ))}
                </ul>
              )}
              <p className={styles.muted}>
                {question.kind === "open" && <strong>A full answer: </strong>}
                <InlineMarkdown text={question.explanation} />
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
