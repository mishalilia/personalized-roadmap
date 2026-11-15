import React, { useEffect, useState, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import {
  ApiError,
  usePathApi,
  type Answers,
  type ExampleProfile,
  type PathApi,
} from "./api";
import { ProgressLine } from "./ProgressLine";
import {
  LEVELS,
  bySection,
  canBeProved,
  completion,
  count,
  isLocked,
  nextUp,
  isLearningPath,
  withChoice,
  type Choice,
  type LearningPath,
  type TimeEstimate,
  type CheckpointSummary,
  type Level,
  type LevelAssessment,
  type PathItem,
  type QuestionsResponse,
  type SavedPath,
} from "./model";
import { CHANGED_EVENT, loadDraft, loadSavedPath, savePath, saveDraft } from "./storage";
import { InlineMarkdown } from "./InlineMarkdown";
import { useModulePages, useVersionLabel } from "./useModulePages";
import styles from "./PersonalPath.module.css";

type Step = "answers" | "level" | "path";

const CHOICE_LABEL: Record<Choice, string> = {
  study: "Study",
  prove: "Prove",
  skip: "Skip",
};

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export default function PersonalPath(): ReactNode {
  const api = usePathApi();
  const [setup, setSetup] = useState<QuestionsResponse | null>(null);
  const [profiles, setProfiles] = useState<ExampleProfile[]>([]);
  // The page renders in the browser only (BrowserOnly), so the stored draft can be read right away.
  const [answers, setAnswersState] = useState<Answers>(loadDraft);
  const setAnswers = (next: Answers) => {
    setAnswersState(next);
    saveDraft(next);
  };
  const [assessment, setAssessment] = useState<LevelAssessment | null>(null);
  const [level, setLevel] = useState<Level>("beginner");
  const [saved, setSaved] = useState<SavedPath | null>(null);
  const [step, setStep] = useState<Step>("answers");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = loadSavedPath();
    if (stored) {
      setSaved(stored);
      setStep("path");
    }
    // Both arrive in one update, so the form does not render again while the learner starts typing.
    if (api)
      Promise.all([api.questions(), api.profiles().catch(() => [] as ExampleProfile[])])
        .then(([questions, examples]) => {
          setProfiles(examples);
          setSetup(questions);
        })
        .catch((reason: unknown) => setError(message(reason)));
    // Progress made on a module page, in this tab or another, shows here too.
    const refresh = () => {
      const current = loadSavedPath();
      if (current) setSaved(current);
    };
    window.addEventListener(CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function run<T>(label: string, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(label);
    setError(null);
    try {
      return await action();
    } catch (reason) {
      setError(message(reason));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function suggestLevel() {
    if (!api) return;
    if (!Object.values(answers).some((answer) => answer.trim())) {
      setError("Answer at least one question first.");
      return;
    }
    const suggestion = await run("Reading your answers…", () => api.level(answers));
    if (suggestion === undefined) return;
    setAssessment(suggestion);
    setLevel(suggestion?.level ?? "beginner");
    setStep("level");
  }

  async function buildPath() {
    if (!api) return;
    const path = await run("Planning your path…", () =>
      api.path(answers, level, assessment),
    );
    if (path) keep(path, setup?.curriculum.site_version ?? null);
  }

  function keep(path: LearningPath, siteVersion: string | null) {
    const next = { path, siteVersion: path.curriculum_site_version ?? siteVersion };
    setSaved(next);
    savePath(next);
    setStep("path");
  }

  function startOver() {
    setSaved(null);
    savePath(null);
    setAnswers({});
    setAssessment(null);
    setStep("answers");
  }

  if (!api) {
    return (
      <p className={styles.notice}>
        Personal paths are not set up on this site: PERSONAL_PATH_API is empty.
      </p>
    );
  }

  return (
    <div className={styles.page}>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {busy && (
        <p className={styles.notice} aria-live="polite">
          {busy}
        </p>
      )}

      {step === "answers" && (
        <AnswersStep
          setup={setup}
          profiles={profiles}
          answers={answers}
          onChange={setAnswers}
          onSubmit={suggestLevel}
          onOpen={(path) => {
            // A path keeps working for as long as the API serves its curriculum version.
            const version = setup?.versions.find((v) => v.version === path.curriculum_version);
            if (version) keep(path, version.site_version);
            else
              setError(
                "This path was planned for a curriculum version that is no longer served. Plan a new one.",
              );
          }}
          onError={setError}
          busy={busy !== null}
        />
      )}
      {step === "level" && (
        <LevelStep
          assessment={assessment}
          level={level}
          onChange={setLevel}
          onBack={() => setStep("answers")}
          onSubmit={buildPath}
          busy={busy !== null}
        />
      )}
      {step === "path" && saved && (
        <PathStep
          api={api}
          saved={saved}
          onChange={(path) => keep(path, saved.siteVersion)}
          onStartOver={startOver}
        />
      )}
    </div>
  );
}

function message(reason: unknown): string {
  return reason instanceof ApiError
    ? reason.message
    : "Something went wrong. Try again later.";
}

function AnswersStep({
  setup,
  profiles,
  answers,
  onChange,
  onSubmit,
  onOpen,
  onError,
  busy,
}: {
  setup: QuestionsResponse | null;
  profiles: ExampleProfile[];
  answers: Answers;
  onChange: (answers: Answers) => void;
  onSubmit: () => void;
  onOpen: (path: LearningPath) => void;
  onError: (message: string) => void;
  busy: boolean;
}) {
  if (!setup) return <p className={styles.notice}>Loading the questions…</p>;
  return (
    <section>
      <h2>1 · About you</h2>
      <p className={styles.lead}>
        Describe what you have done, not how you rate yourself. Short answers are fine, and you can
        leave a question empty.
      </p>
      {!setup.personalization_available && (
        <p className={styles.notice}>
          Personalization is unavailable right now, so your path will be the whole course in its
          own order.
        </p>
      )}
      {profiles.length > 0 && (
        <label className={styles.question}>
          <span>Answer the questions yourself, or start from an invented example learner</span>
          <select
            className={styles.select}
            defaultValue=""
            onChange={(event) => {
              const profile = profiles.find((candidate) => candidate.id === event.target.value);
              onChange(profile ? { ...profile.answers } : {});
            }}
          >
            <option value="">My own answers</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.title}
              </option>
            ))}
          </select>
        </label>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        {setup.questions.map((question) => (
          <label key={question.id} className={styles.question}>
            <span>{question.text}</span>
            <textarea
              rows={3}
              maxLength={2000}
              placeholder={question.placeholder}
              value={answers[question.id] ?? ""}
              onChange={(event) =>
                onChange({ ...answers, [question.id]: event.target.value })
              }
            />
          </label>
        ))}
        <p className={styles.small}>
          Your answers are sent to the Personalized Roadmap service and its language model provider
          to plan the path. They are not stored there. The path is kept in this browser only.
        </p>
        <div className={styles.actions}>
          <button type="submit" className="button button--primary" disabled={busy}>
            Suggest my level
          </button>
          <OpenFile onOpen={onOpen} onError={onError} />
        </div>
      </form>
    </section>
  );
}

function LevelStep({
  assessment,
  level,
  onChange,
  onBack,
  onSubmit,
  busy,
}: {
  assessment: LevelAssessment | null;
  level: Level;
  onChange: (level: Level) => void;
  onBack: () => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  return (
    <section>
      <h2>2 · Your level</h2>
      {assessment ? (
        <>
          <p>
            Suggested level: <strong>{capitalize(assessment.level)}</strong> ·{" "}
            {assessment.confidence} confidence
          </p>
          <ul>
            {assessment.evidence.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <p className={styles.small}>
            This is a suggestion, not a verdict. If it is wrong, change it: your path is planned
            for the level you choose.
          </p>
        </>
      ) : (
        <p className={styles.notice}>
          A level could not be suggested right now. Choose the one that fits you best.
        </p>
      )}
      <fieldset className={styles.levels}>
        <legend>Plan my path for</legend>
        {LEVELS.map((option) => (
          <label key={option}>
            <input
              type="radio"
              name="level"
              checked={level === option}
              onChange={() => onChange(option)}
            />{" "}
            {capitalize(option)}
          </label>
        ))}
      </fieldset>
      <div className={styles.actions}>
        <button type="button" className="button button--primary" onClick={onSubmit} disabled={busy}>
          Build my path
        </button>
        <button type="button" className="button button--outline button--primary" onClick={onBack} disabled={busy}>
          Back to the questions
        </button>
      </div>
    </section>
  );
}

function PathStep({
  api,
  saved,
  onChange,
  onStartOver,
}: {
  api: PathApi;
  saved: SavedPath;
  onChange: (path: LearningPath) => void;
  onStartOver: () => void;
}) {
  const { path, siteVersion } = saved;
  const pageOf = useModulePages(siteVersion);
  const versionLabel = useVersionLabel(siteVersion);
  const changed = path.items.filter((item) => item.choice !== item.suggested).length;
  const [checkpoints, setCheckpoints] = useState<Record<string, CheckpointSummary>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  useEffect(() => {
    api.checkpoints(path.curriculum_version).then(setCheckpoints).catch(() => setCheckpoints({}));
  }, [api, path.curriculum_version]);
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const next = path.confirmed_at ? nextUp(path) : undefined;
  const estimate = path.time_estimate;
  const { finished, total } = completion(path);
  const blocking = path.items.find((item) => item.module.id === path.blocking_module_id);
  const titleOf = (moduleId: string) =>
    path.items.find((item) => item.module.id === moduleId)?.module.title ?? moduleId;

  async function act(action: "accept" | "decline", moduleId: string) {
    setActionError(null);
    try {
      onChange(await api.act(action, path, moduleId));
    } catch (reason) {
      setActionError(message(reason));
    }
  }

  async function call(label: string, action: () => Promise<LearningPath>) {
    setActionError(null);
    setBusy(label);
    try {
      onChange(await action());
      return true;
    } catch (reason) {
      setActionError(message(reason));
      return false;
    } finally {
      setBusy(null);
    }
  }

  // Sharing starts counting from a confirmation, so turning it on for a confirmed path confirms it again.
  async function share(on: boolean) {
    const changed = { ...path, share_progress: on };
    if (on && path.confirmed_at) await call("Saving…", () => api.confirm(changed));
    else onChange(changed);
  }

  return (
    <section>
      <h2>3 · Your path</h2>
      {path.personalization_unavailable && (
        <p className={styles.notice}>
          Personalization was unavailable, so this path follows the course as written.
        </p>
      )}
      <p className={styles.small}>
        Planned for: <strong>{path.level ? capitalize(path.level) : "no level"}</strong>
        {versionLabel && <> · curriculum version: {versionLabel}</>}. The planner only suggests:
        change what you do with any module, and your choice replaces its suggestion.
      </p>
      {path.answers?.goal && (
        <p className={styles.small}>
          Your goal: <strong>{path.answers.goal}</strong>
        </p>
      )}
      {next && (
        <div className={styles.next}>
          <span className={styles.small}>Next up</span>
          <strong>{next.module.title}</strong>
          <span className={styles.small}>
            {next.choice === "prove" ? "Prove it" : "Study it"}
            {next.module.hours && ` · about ${hours(next.module.hours.low, next.module.hours.high)}`}
          </span>
          {pageOf(next.module.id) && <Link to={pageOf(next.module.id)!}>Open the module</Link>}
        </div>
      )}
      <div className={styles.counts}>
        <Count label="To study" value={count(path, "study")} />
        <Count label="To prove" value={count(path, "prove")} />
        <Count label="Skipped" value={count(path, "skip")} />
        <Count label="Changed by you" value={changed} />
      </div>
      {/* A total over a minority of the modules would read as the time for the whole path. */}
      {estimate && estimate.course_high > 0 && !mostlyEstimated(path, estimate) && (
        <p className={styles.small}>
          Time: the curriculum states a workload for only{" "}
          {included(path) - estimate.modules_without_estimate} of the {included(path)} modules in your
          path, so no total is shown.
        </p>
      )}
      {estimate && estimate.course_high > 0 && mostlyEstimated(path, estimate) && (
        <p className={styles.small}>
          Time: about <strong>{hours(estimate.path_low, estimate.path_high)}</strong> for your path,
          against {hours(estimate.course_low, estimate.course_high)} for the whole course
          {estimate.modules_without_estimate > 0 &&
            `, not counting ${estimate.modules_without_estimate} module${
              estimate.modules_without_estimate === 1 ? "" : "s"
            } in your path that state${estimate.modules_without_estimate === 1 ? "s" : ""} no workload`}
          . Estimates come from the curriculum: the authors' workload, or the durations of a module's
          resources.
        </p>
      )}

      {path.confirmed_at && (
        <div className={styles.progress}>
          <p>
            <strong>
              Completed {finished} of {total} modules
            </strong>{" "}
            · take each module's checkpoint on its page, or mark a module without one as done.
          </p>
          <progress max={total} value={finished} aria-label="Modules completed" />
          {blocking && (
            <p className={styles.locked}>
              🔒 The modules after <strong>{blocking.module.title}</strong> are locked until you pass
              its checkpoint.
            </p>
          )}
        </div>
      )}

      {(path.proposals ?? []).length > 0 && (
        <div className={styles.proposals}>
          <h3>Suggested after your last checkpoint</h3>
          <p className={styles.small}>
            You passed a checkpoint without a mistake, so these modules may need less of your time.
            Nothing changes unless you accept.
          </p>
          {(path.proposals ?? []).map((proposal) => (
            <div key={proposal.module_id} className={styles.proposal}>
              <span>
                <strong>{titleOf(proposal.module_id)}</strong>: {proposal.choice} it.{" "}
                {proposal.reason}
              </span>
              <span>
                <button
                  type="button"
                  className="button button--primary button--sm"
                  onClick={() => void act("accept", proposal.module_id)}
                >
                  Accept
                </button>{" "}
                <button
                  type="button"
                  className="button button--outline button--primary button--sm"
                  onClick={() => void act("decline", proposal.module_id)}
                >
                  Decline
                </button>
              </span>
            </div>
          ))}
          {actionError && <p className={styles.error}>{actionError}</p>}
        </div>
      )}

      {bySection(path.items).map(({ section, items }) => {
        const content = items.map((item) => (
          <ModuleCard
            key={item.module.id}
            item={item}
            href={pageOf(item.module.id)}
            started={path.confirmed_at !== null}
            locked={isLocked(path, item.module.id)}
            hasCheckpoint={item.module.id in checkpoints}
            onChoose={(choice) => onChange(withChoice(path, item.module.id, choice))}
          />
        ));
        return items.some((item) => item.choice !== "skip") ? (
          <div key={section} className={styles.section}>
            <h3>{section}</h3>
            {content}
          </div>
        ) : (
          <details key={section} className={styles.section}>
            <summary>{section} · skipped</summary>
            {content}
          </details>
        );
      })}

      <div className={styles.confirm}>
        {path.confirmed_at ? (
          <p>
            ✓ You confirmed this path on {new Date(path.confirmed_at).toLocaleString()}. Each
            module page now shows what you decided for it.
          </p>
        ) : (
          <p>Check the decisions, then confirm the path to use it on the module pages.</p>
        )}
        <div className={styles.actions}>
          {!path.confirmed_at && (
            <button
              type="button"
              className="button button--primary"
              disabled={busy !== null}
              onClick={() => void call("Confirming…", () => api.confirm(path))}
            >
              Confirm my path
            </button>
          )}
          <button
            type="button"
            className="button button--outline button--primary"
            disabled={!path.confirmed_at}
            onClick={() => download(path)}
          >
            Download as JSON
          </button>
          <button type="button" className="button button--link" onClick={onStartOver}>
            Start over
          </button>
        </div>
        <label className={styles.share}>
          <input
            type="checkbox"
            checked={path.share_progress ?? false}
            disabled={busy !== null}
            onChange={(event) => void share(event.target.checked)}
          />{" "}
          Share my progress anonymously with the course authors: which modules I finish, fail or stop
          at. Never my answers, my level or anything that identifies me. You can turn it off at any
          time; what was already shared stays counted.
        </label>
        {actionError && <p className={styles.error}>{actionError}</p>}
      </div>

      <form
        className={styles.goal}
        onSubmit={(event) => {
          event.preventDefault();
          void call("Planning the rest of your path for the new goal…", () =>
            api.changeGoal(path, goal),
          ).then((ok) => ok && setGoal(""));
        }}
      >
        <h3>Changed your mind about the goal?</h3>
        <p className={styles.small}>
          The rest of your path is planned again for the new goal. Modules you have started keep their
          decision and progress. Check the new path and confirm it again.
        </p>
        <textarea
          rows={2}
          value={goal}
          maxLength={2000}
          placeholder="e.g. Build speech recognition for Uzbek instead of computer vision."
          onChange={(event) => setGoal(event.target.value)}
        />
        <button
          type="submit"
          className="button button--outline button--primary button--sm"
          disabled={goal.trim().length < 3 || busy !== null}
        >
          Plan for this goal
        </button>
        {busy && <p className={styles.small}>{busy}</p>}
      </form>

      <p className={styles.small}>
        Learning content: <a href={path.attribution.url}>{path.attribution.title}</a> by{" "}
        {path.attribution.author}, licensed under{" "}
        <a href={path.attribution.licence_url}>{path.attribution.licence}</a>. {path.changes}
      </p>
    </section>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.count}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ModuleCard({
  item,
  href,
  started,
  locked,
  hasCheckpoint,
  onChoose,
}: {
  item: PathItem;
  href: string | undefined;
  started: boolean;
  locked: boolean;
  hasCheckpoint: boolean;
  onChoose: (choice: Choice) => void;
}) {
  const choices: Choice[] = canBeProved(item) ? ["study", "prove", "skip"] : ["study", "skip"];
  return (
    <article className={styles.card} data-choice={item.choice}>
      <header className={styles.cardHeader}>
        <h4>{href ? <Link to={href}>{item.module.title}</Link> : item.module.title}</h4>
        <div className={styles.choices} role="radiogroup" aria-label={`${item.module.title}: what to do`}>
          {choices.map((choice) => (
            <label key={choice}>
              <input
                type="radio"
                name={item.module.id}
                checked={item.choice === choice}
                onChange={() => onChoose(choice)}
              />{" "}
              {CHOICE_LABEL[choice]}
            </label>
          ))}
        </div>
      </header>
      <p className={styles.reason}>
        {item.adjustment ??
          (item.choice === item.suggested
            ? item.reason
            : `You chose to ${item.choice} it. The planner suggested ${item.suggested}: ${item.reason}`)}
      </p>
      {started && item.choice !== "skip" && (
        <p className={styles.status}>
          {locked ? (
            <span className={styles.locked}>🔒 Locked</span>
          ) : (
            <>
              <ProgressLine item={item} />
              {item.progress !== "passed" && item.progress !== "done" && href && (
                <Link to={href}>
                  {hasCheckpoint ? "Take the checkpoint on the module page" : "Open the module"}
                </Link>
              )}
            </>
          )}
        </p>
      )}
      {item.choice === "prove" && (
        <div className={styles.checklist}>
          <p>
            <strong>Prove it instead of studying it.</strong> If you can already do everything
            below{hasCheckpoint && " and pass the module's checkpoint"}, you do not need this module;
            if you cannot, study it.
          </p>
          <ul>
            {item.module.checklist.map((line) => (
              <li key={line}>
                <InlineMarkdown text={line} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

function OpenFile({
  onOpen,
  onError,
}: {
  onOpen: (path: LearningPath) => void;
  onError: (message: string) => void;
}) {
  return (
    <label className="button button--outline button--primary">
      Open a saved path
      <input
        type="file"
        accept="application/json,.json"
        hidden
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          try {
            const value: unknown = JSON.parse(await file.text());
            if (isLearningPath(value)) onOpen(value);
            else onError("This file is not a personal path.");
          } catch {
            onError("This file is not a personal path.");
          }
        }}
      />
    </label>
  );
}

function download(path: LearningPath) {
  const blob = new Blob([JSON.stringify(path, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "personal-path.json";
  link.click();
  URL.revokeObjectURL(url);
}

function included(path: LearningPath): number {
  return count(path, "study") + count(path, "prove");
}

// True when at least half of the modules the learner works through state a workload.
function mostlyEstimated(path: LearningPath, estimate: TimeEstimate): boolean {
  return (included(path) - estimate.modules_without_estimate) * 2 >= included(path);
}

function hours(low: number, high: number): string {
  const round = (value: number) => (value < 10 ? Math.round(value * 2) / 2 : Math.round(value));
  return round(low) === round(high) ? `${round(low)} h` : `${round(low)}–${round(high)} h`;
}
