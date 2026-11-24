// The personal path page: onboarding until the learner has a path, then the path itself, which they review,
// confirm and follow from the module pages.
import React, { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import useBaseUrl from "@docusaurus/useBaseUrl";
import clsx from "clsx";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  CircleCheck,
  Clock,
  Link2,
  ListChecks,
  Lock,
  RotateCcw,
  Sparkles,
  Target,
} from "lucide-react";
import { Collapsible } from "@docusaurus/theme-common";
import ModuleTopics from "./ModuleTopics";
import {
  message,
  usePathApi,
  type Answer,
  type Answers,
  type ChoiceAnswer,
  type ExampleProfile,
  type PathApi,
} from "./api";
import { InlineMarkdown } from "./InlineMarkdown";
import {
  LEVELS,
  bySection,
  canBeProved,
  topicsToReview,
  completion,
  count,
  hours,
  isIncluded,
  nextUp,
  proposalAction,
  statusOf,
  type Choice,
  type LearningPath,
  type Level,
  type LevelAssessment,
  type PathItem,
  type Proposal,
  type Question,
  type QuestionsResponse,
} from "./model";
import {
  handleSignedOut,
  openAuth,
  setDraft,
  setPath,
  startSession,
  useCheckpoints,
  usePathState,
} from "./store";
import { changePath, withChoice } from "./changes";
import { useModulePages, useVersionLabel } from "./useModulePages";
import {
  CHOICE_HINT,
  CHOICE_LABEL,
  ChoiceChip,
  ProgressBar,
  ProgressRing,
  ReviewTopics,
  Spinner,
  StatusIcon,
  SmoothHeight,
} from "./ui";
import styles from "./path.module.css";

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

const LEVEL_HINT: Record<Level, string> = {
  beginner: "New to programming or to most of the course's topics.",
  intermediate: "You program comfortably and know some of the topics.",
  advanced: "You build software for a living and know most of the topics.",
};

export default function PersonalPath(): ReactNode {
  const api = usePathApi();
  const { ready, path } = usePathState();

  useEffect(() => {
    if (api) void startSession(api);
  }, [api]);

  if (!api)
    return (
      <p className={styles.panel} data-tone="muted">
        Personal paths are not set up on this site: PERSONAL_PATH_API is empty.
      </p>
    );
  if (!ready)
    return (
      <div className={styles.loadingPage}>
        <Spinner /> Loading…
      </div>
    );
  // Sized by its container: the same view fits the side panel and a full page.
  return (
    <div className={styles.ppRoot}>
      {path ? <PathView api={api} path={path} /> : <Onboarding api={api} />}
    </div>
  );
}

// Onboarding: one question at a time, then the level, then planning.

const ANSWERS_KEY = "humblebeeai.personal-path.answers";

function loadAnswers(): Answers {
  try {
    return JSON.parse(window.localStorage.getItem(ANSWERS_KEY) ?? "{}") as Answers;
  } catch {
    return {};
  }
}

function keepAnswers(answers: Answers | null): void {
  try {
    if (answers) window.localStorage.setItem(ANSWERS_KEY, JSON.stringify(answers));
    else window.localStorage.removeItem(ANSWERS_KEY);
  } catch {
    // Not remembered; the form still works.
  }
}

type Stage = { kind: "question"; index: number } | { kind: "level" } | { kind: "planning" };

// An answer kept from before a question had options counts as its details.
function asChoice(answer: Answer | undefined): ChoiceAnswer {
  if (answer === undefined) return { choices: [], details: "" };
  return typeof answer === "string" ? { choices: [], details: answer } : answer;
}

function isAnswered(answer: Answer | undefined): boolean {
  if (answer === undefined) return false;
  return typeof answer === "string"
    ? answer.trim() !== ""
    : answer.choices.length > 0 || answer.details.trim() !== "";
}

// What the API is sent: text for a text question, choices and details for the others.
function answersFor(questions: Question[], answers: Answers): Answers {
  const sent: Answers = {};
  for (const question of questions) {
    const answer = answers[question.id];
    if (!isAnswered(answer)) continue;
    sent[question.id] = question.kind === "text" ? (typeof answer === "string" ? answer : asChoice(answer).details) : asChoice(answer);
  }
  return sent;
}

// Choosing an option: one for single and code questions; any number for multiple, where "none" stands alone.
function toggled(question: Question, choices: string[], option: string): string[] {
  if (question.kind !== "multiple") return [option];
  if (choices.includes(option)) return choices.filter((choice) => choice !== option);
  if (option === "none") return ["none"];
  return [...choices.filter((choice) => choice !== "none"), option];
}

const QUESTION_HINT: Record<Question["kind"], string> = {
  text: "Short answers are fine; leave it empty to skip the question.",
  single:
    "Choose what fits best. The details are optional, but they make the suggested level more precise. Leave it empty to skip the question.",
  multiple:
    "Tick everything you have used. The details are optional, but they make the suggested level more precise.",
  check: "Answer without running the code. A wrong answer is fine: it only helps suggest your level.",
};

function sameAnswers(answers: Answers, example: Answers): boolean {
  const ids = new Set([...Object.keys(answers), ...Object.keys(example)]);
  return [...ids].every((id) => JSON.stringify(answers[id] ?? null) === JSON.stringify(example[id] ?? null));
}

function Onboarding({ api }: { api: PathApi }): ReactNode {
  const [setup, setSetup] = useState<QuestionsResponse | null>(null);
  const [profiles, setProfiles] = useState<ExampleProfile[]>([]);
  const [answers, setAnswersState] = useState<Answers>(loadAnswers);
  const [stage, setStage] = useState<Stage>({ kind: "question", index: 0 });
  const [assessment, setAssessment] = useState<LevelAssessment | null>(null);
  const [level, setLevel] = useState<Level>("beginner");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const cardTop = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([api.questions(), api.profiles().catch(() => [] as ExampleProfile[])])
      .then(([questions, examples]) => {
        setProfiles(examples);
        setSetup(questions);
      })
      .catch((reason: unknown) => setError(message(reason)));
  }, [api]);

  useEffect(() => {
    // Each step starts at the top of the card, with the first field ready for typing.
    field.current?.focus({ preventScroll: true });
    cardTop.current?.scrollIntoView({ block: "nearest" });
  }, [stage, setup]);

  const setAnswers = (next: Answers) => {
    setAnswersState(next);
    keepAnswers(next);
  };

  async function suggestLevel() {
    if (!Object.values(answers).some(isAnswered)) {
      setError("Answer at least one question first.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const suggestion = await api.level(answersFor(questions, answers));
      setAssessment(suggestion);
      setLevel(suggestion?.level ?? "beginner");
      setStage({ kind: "level" });
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function plan() {
    setError(null);
    setStage({ kind: "planning" });
    try {
      const planned = await api.plan(answersFor(questions, answers), level, assessment);
      keepAnswers(null);
      if (planned.draft_id) setDraft(planned.path, planned.draft_id);
      else setPath(planned.path);
      window.scrollTo({ top: 0 });
    } catch (reason) {
      setError(message(reason));
      setStage({ kind: "level" });
    }
  }

  const questions = setup?.questions ?? [];
  const stepNumber = stage.kind === "question" ? 1 : stage.kind === "level" ? 2 : 3;

  function questionStep(index: number): ReactNode {
    const question = questions[index];
    const last = index === questions.length - 1;
    const answered = isAnswered(answers[question.id]);
    const choice = asChoice(answers[question.id]);
    const submitOnCtrlEnter = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        next();
      }
    };
    const next = () => (last ? void suggestLevel() : setStage({ kind: "question", index: index + 1 }));
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          next();
        }}
      >
        <div className={styles.questionHead}>
          <span className={styles.muted}>
            Question {index + 1} of {questions.length}
          </span>
          <ProgressBar finished={index} total={questions.length} />
        </div>
        {question.kind === "text" ? (
          <label className={styles.bigQuestion}>
            <span>{question.text}</span>
            <textarea
              ref={field}
              rows={4}
              maxLength={2000}
              placeholder={question.placeholder}
              value={typeof answers[question.id] === "string" ? (answers[question.id] as string) : choice.details}
              onChange={(event) => setAnswers({ ...answers, [question.id]: event.target.value })}
              onKeyDown={submitOnCtrlEnter}
            />
          </label>
        ) : (
          <fieldset className={styles.choiceQuestion}>
            <legend>{question.text}</legend>
            {question.code && (
              <pre className={styles.onboardingCode}>
                <code>{question.code}</code>
              </pre>
            )}
            <div className={styles.choiceList}>
              {question.options.map((option) => {
                const on = choice.choices.includes(option.id);
                return (
                  <label key={option.id} className={clsx(styles.choiceOption, on && styles.choiceOn)}>
                    <input
                      type={question.kind === "multiple" ? "checkbox" : "radio"}
                      name={question.id}
                      checked={on}
                      onChange={() =>
                        setAnswers({
                          ...answers,
                          [question.id]: { ...choice, choices: toggled(question, choice.choices, option.id) },
                        })
                      }
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
            {question.kind !== "check" && (
              <textarea
                rows={2}
                maxLength={2000}
                aria-label="Details, optional"
                placeholder={question.placeholder}
                value={choice.details}
                onChange={(event) =>
                  setAnswers({ ...answers, [question.id]: { ...choice, details: event.target.value } })
                }
                onKeyDown={submitOnCtrlEnter}
              />
            )}
          </fieldset>
        )}
        <p className={styles.fine}>{QUESTION_HINT[question.kind]}</p>
        <div className={styles.navRow}>
          <button
            type="button"
            className={styles.ghost}
            disabled={index === 0}
            onClick={() => setStage({ kind: "question", index: index - 1 })}
          >
            <ArrowLeft size={16} aria-hidden /> Back
          </button>
          <button type="submit" className={answered || last ? styles.primary : styles.ghost} disabled={busy}>
            {busy && <Spinner />}
            {last ? "See my level" : answered ? "Next" : "Skip"}
            {!busy && <ArrowRight size={16} aria-hidden />}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className={styles.onboarding}>
      <header className={styles.hero}>
        <span className={styles.eyebrow}>Personal path</span>
        <h1>Find your way through the course</h1>
        <p className={styles.lead}>
          Tell us what you have done and what you want to do. For every module you get a suggestion — study
          it, prove you already know it, or skip it — with a reason. You stay in charge of every decision.
        </p>
        <ol className={styles.stepper} aria-label="Steps">
          {["About you", "Your level", "Your path"].map((label, index) => (
            <li
              key={label}
              data-state={index + 1 < stepNumber ? "done" : index + 1 === stepNumber ? "current" : "todo"}
              aria-current={index + 1 === stepNumber ? "step" : undefined}
            >
              <span>{index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
      </header>
      <div ref={cardTop} style={{ scrollMarginTop: "calc(var(--ifm-navbar-height) + 1rem)" }} />

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {!setup ? (
        !error && (
          <div className={styles.card}>
            <Spinner /> Loading the questions…
          </div>
        )
      ) : stage.kind === "question" ? (
        <div className={styles.card}>
          {!setup.personalization_available && (
            <p className={styles.panel} data-tone="muted">
              Personalization is unavailable right now, so your path will be the whole course in its own
              order.
            </p>
          )}
          {stage.index === 0 && profiles.length > 0 && (
            <div className={styles.examples}>
              <span className={styles.muted}>Just looking around? Fill in an invented example learner:</span>
              {profiles.map((profile) => (
                <button
                  key={profile.id}
                  type="button"
                  className={styles.exampleChip}
                  // Lit while the answers are this example's: it stays so after a reload, and goes out once
                  // the learner changes an answer.
                  aria-pressed={sameAnswers(answers, profile.answers)}
                  onClick={() => setAnswers({ ...profile.answers })}
                >
                  {profile.title}
                </button>
              ))}
            </div>
          )}
          {questionStep(stage.index)}
          <p className={styles.fine}>
            Your answers go to the Personalized Roadmap service and its language model provider to plan the
            path. If you create an account, your path and these answers are kept with it until you delete it.
          </p>
        </div>
      ) : stage.kind === "level" ? (
        <div className={styles.card}>
          {assessment ? (
            <div className={styles.assessment}>
              <span className={styles.eyebrow}>Suggested level · {assessment.confidence} confidence</span>
              <h2>{capitalize(assessment.level)}</h2>
              <ul>
                {assessment.evidence.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className={styles.panel} data-tone="muted">
              A level could not be suggested right now. Choose the one that fits you best.
            </p>
          )}
          <fieldset className={styles.levelCards}>
            <legend>Plan my path for</legend>
            {LEVELS.map((option) => (
              <label key={option} className={clsx(styles.levelCard, level === option && styles.levelCardOn)}>
                <input
                  type="radio"
                  name="level"
                  checked={level === option}
                  onChange={() => setLevel(option)}
                />
                <strong>
                  {capitalize(option)}
                  {assessment?.level === option && <span className={styles.tag}>Suggested</span>}
                </strong>
                <span className={styles.muted}>{LEVEL_HINT[option]}</span>
              </label>
            ))}
          </fieldset>
          <p className={styles.fine}>
            A suggestion, not a verdict: your path is planned for the level you choose.
          </p>
          <div className={styles.navRow}>
            <button
              type="button"
              className={styles.ghost}
              onClick={() => setStage({ kind: "question", index: questions.length - 1 })}
            >
              <ArrowLeft size={16} aria-hidden /> Back
            </button>
            <button type="button" className={styles.primary} onClick={() => void plan()}>
              Build my path <ArrowRight size={16} aria-hidden />
            </button>
          </div>
        </div>
      ) : (
        <div className={clsx(styles.card, styles.planning)} aria-live="polite">
          <Spinner />
          <strong>Planning your path…</strong>
          <span className={styles.muted}>
            Going through every module of the course with your answers. This can take up to a minute.
          </span>
        </div>
      )}
    </div>
  );
}

// The path: review, confirm, follow.

function PathView({ api, path }: { api: PathApi; path: LearningPath }): ReactNode {
  const { account, confirmCall } = usePathState();
  const siteVersion = path.curriculum_site_version ?? null;
  const pageOf = useModulePages(siteVersion);
  const versionLabel = useVersionLabel(siteVersion);
  const checkpoints = useCheckpoints(api, path.curriculum_version);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const signedIn = account !== null;
  const confirmed = path.confirmed_at !== null;
  const { finished, total } = completion(path);
  const next = confirmed ? nextUp(path) : undefined;
  const blocking = path.items.find((item) => item.module.id === path.blocking_module_id);
  const sections = useMemo(() => bySection(path.items), [path.items]);
  const estimate = path.time_estimate;
  const working = count(path, "study") + count(path, "prove");
  const estimated = estimate ? working - estimate.modules_without_estimate : 0;

  // "Review and confirm your path" pressed elsewhere on the page while this is open: bring the confirmation
  // into view and make it blink, so the learner sees where to go. Not on mounting, which a new page also does.
  const callout = useRef<HTMLDivElement>(null);
  const seenCall = useRef(confirmCall);
  useEffect(() => {
    if (confirmCall === seenCall.current) return;
    seenCall.current = confirmCall;
    const banner = callout.current;
    if (!banner) return;
    banner.scrollIntoView({ block: "nearest", behavior: "smooth" });
    banner.removeAttribute("data-flash");
    void banner.offsetWidth; // restart the animation when pressed again
    banner.setAttribute("data-flash", "true");
  }, [confirmCall]);

  async function run(label: string, action: () => Promise<LearningPath | void>): Promise<boolean> {
    setBusy(label);
    setError(null);
    try {
      const result = await action();
      if (result) setPath(result);
      return true;
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
      return false;
    } finally {
      setBusy(null);
    }
  }

  function choose(item: PathItem, choice: Choice) {
    if (!signedIn) return openAuth("sign-up", "Create an account to change and keep your path.");
    if (choice === item.choice) return;
    changePath(
      api,
      (current) => withChoice(current, item.module.id, choice),
      () => api.choose(item.module.id, choice),
      setError,
    );
  }


  return (
    <div className={styles.pathPage}>
      <header className={styles.pathHeader}>
        <div>
          <span className={styles.eyebrow}>My path</span>
          <h1>{path.title ?? path.answers?.goal ?? "Your path through the course"}</h1>
          <p className={styles.muted}>
            Planned for {path.level ? <strong>{capitalize(path.level)}</strong> : "no particular level"}
            {versionLabel && <> · curriculum: {versionLabel}</>}
            {path.personalization_unavailable &&
              " · personalization was unavailable, so this is the whole course"}
          </p>
        </div>
        {confirmed && (
          <div className={styles.headerProgress}>
            <ProgressRing finished={finished} total={total} size={76} />
            <span className={styles.muted}>
              {finished} of {total} modules
            </span>
          </div>
        )}
      </header>

      {!signedIn ? (
        <div ref={callout} className={styles.banner} data-tone="gold">
          <Sparkles size={20} aria-hidden />
          <div>
            <strong>Your path is ready. Save it to start.</strong>
            <p>
              Create a free account to keep this path, adjust it, take checkpoints and track your progress.
              Without one, it is kept for 24 hours.
            </p>
          </div>
          <div className={styles.actions}>
            <button type="button" className={styles.primary} onClick={() => openAuth("sign-up")}>
              Create account
            </button>
            <button type="button" className={styles.ghost} onClick={() => openAuth("sign-in")}>
              Sign in
            </button>
          </div>
        </div>
      ) : (
        !confirmed && (
          <div ref={callout} className={clsx(styles.banner, styles.sticky)} data-tone="gold">
            <ListChecks size={20} aria-hidden />
            <div>
              <strong>Review your path, then confirm it</strong>
              <p>
                The planner only suggests: change what you do with any module below. Confirming starts your
                progress and shows your path on every module page.
              </p>
            </div>
            <button
              type="button"
              className={styles.primary}
              disabled={busy !== null}
              onClick={() => void run("confirm", () => api.confirm())}
            >
              {busy === "confirm" && <Spinner />} Confirm my path
            </button>
          </div>
        )
      )}

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {next && (
        <Link to={pageOf(next.module.id) ?? "/docs/"} className={styles.continue}>
          <span className={styles.eyebrow}>
            {finished === 0 ? "Start here" : "Continue where you left off"}
          </span>
          <strong>{next.module.title}</strong>
          <span className={styles.continueMeta}>
            <ChoiceChip choice={next.choice} />
            {next.module.id in checkpoints && <span>Checkpoint at the end</span>}
            {next.module.hours && <span>about {hours(next.module.hours.low, next.module.hours.high)}</span>}
          </span>
          <span className={styles.continueGo}>
            Open the module <ArrowRight size={16} aria-hidden />
          </span>
        </Link>
      )}
      {confirmed && finished === total && total > 0 && (
        <div className={styles.banner} data-tone="success">
          <strong>🎉 You have completed every module in your path.</strong>
        </div>
      )}
      {blocking && (
        <p className={styles.lockNote}>
          <Lock size={15} aria-hidden /> The modules after <strong>{blocking.module.title}</strong> are locked
          until you pass its checkpoint.
        </p>
      )}

      <Proposals api={api} path={path} onError={setError} />

      <div className={styles.stats}>
        <Stat label="To study" value={count(path, "study")} choice="study" />
        <Stat label="To prove" value={count(path, "prove")} choice="prove" />
        <Stat label="Skipped" value={count(path, "skip")} choice="skip" />
        {/* Shown only when the course states a workload for most of the modules: a total over a few of them
            would read as the time for the whole path. */}
        {estimate && estimate.course_high > 0 && estimated * 2 >= working && (
          <div className={styles.stat}>
            <span>
              <Clock size={14} aria-hidden /> Time
            </span>
            <strong>{hours(estimate.path_low, estimate.path_high)}</strong>
            <small>of {hours(estimate.course_low, estimate.course_high)} for the whole course</small>
          </div>
        )}
      </div>

      <div className={styles.legend}>
        {(["study", "prove", "skip"] as Choice[]).map((choice) => (
          <span key={choice}>
            <ChoiceChip choice={choice} /> {CHOICE_HINT[choice]}
          </span>
        ))}
      </div>

      {/* The path as a road: each section of the course is a stage, each module a stop on it. A stop opens to
          show why it is in the path and what the learner can do with it. */}
      <ol className={styles.roadmap} aria-label="Your path, section by section">
        {sections.map(({ section, items }) => {
          const kept = items.filter(isIncluded).length;
          const nodes = items.map((item) => (
            <RoadmapNode
              key={item.module.id}
              path={path}
              item={item}
              href={pageOf(item.module.id)}
              hasCheckpoint={item.module.id in checkpoints}
              busy={false}
              onChoose={(choice) => choose(item, choice)}
            />
          ));
          // "Soft Landing Program › Specializations › Computer Vision": the stage is named by its last part,
          // with the parts above it as a small line over the name.
          const parts = section.split(" › ");
          const name = parts.pop();
          return (
            <li key={section} className={styles.stage} data-skipped={kept === 0}>
              <div className={styles.stageHead}>
                <span className={styles.stageMark} aria-hidden />
                <div className={styles.stageText}>
                  {parts.length > 0 && <span className={styles.stageParent}>{parts.join(" › ")}</span>}
                  <h2>{name}</h2>
                  <span className={styles.muted}>
                    {kept === 0
                      ? `skipped · ${items.length} modules`
                      : `${kept} of ${items.length} in your path`}
                  </span>
                </div>
              </div>
              <StageStops skipped={kept === 0}>{nodes}</StageStops>
            </li>
          );
        })}
      </ol>

      {signedIn && <Settings api={api} path={path} busy={busy} run={run} />}

      <p className={styles.fine}>
        Learning content: <a href={path.attribution.url}>{path.attribution.title}</a> by{" "}
        {path.attribution.author}, licensed under{" "}
        <a href={path.attribution.licence_url}>{path.attribution.licence}</a>. {path.changes}
      </p>
    </div>
  );
}

function Stat({ label, value, choice }: { label: string; value: number; choice: Choice }): ReactNode {
  return (
    <div className={styles.stat} data-choice={choice}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>modules</small>
    </div>
  );
}

function RoadmapNode({
  path,
  item,
  href,
  hasCheckpoint,
  busy,
  onChoose,
}: {
  path: LearningPath;
  item: PathItem;
  href: string | undefined;
  hasCheckpoint: boolean;
  busy: boolean;
  onChoose: (choice: Choice) => void;
}): ReactNode {
  const choices: Choice[] = canBeProved(item) ? ["study", "prove", "skip"] : ["study", "skip"];
  const status = statusOf(path, item);
  // The stop the learner is on, or one that needs another try, is open from the start; the rest open on a click.
  const [open, setOpen] = useState(status === "next" || status === "failed" || status === "returned");
  const reason =
    item.adjustment ??
    (item.choice === item.suggested
      ? item.reason
      : `Your own choice. The planner suggested to ${item.suggested} it: ${item.reason}`);
  const detailsId = `stop-${item.module.id.replace(/[^a-z0-9]+/gi, "-")}`;
  return (
    <li className={styles.node} data-status={status} data-choice={item.choice} data-open={open}>
      <span className={styles.nodeMark}>
        <StatusIcon status={path.confirmed_at || status === "skipped" ? status : "todo"} />
      </span>
      <div className={styles.nodeCard}>
        <div className={styles.nodeHead} onClick={() => setOpen(!open)}>
          <div className={styles.nodeText}>
            <span className={styles.nodeTitle}>
              {href ? (
                <Link to={href} onClick={(event) => event.stopPropagation()}>
                  {item.module.title}
                </Link>
              ) : (
                item.module.title
              )}
            </span>
            <span className={styles.nodeMeta}>
              <ChoiceChip choice={item.choice} />
              {item.choice !== "skip" && item.module.hours && (
                <span>
                  <Clock size={12} aria-hidden /> {hours(item.module.hours.low, item.module.hours.high)}
                </span>
              )}
              {item.choice !== "skip" && hasCheckpoint && <span>Checkpoint</span>}
              {item.choice !== item.suggested && <span>changed by you</span>}
            </span>
          </div>
          <button
            type="button"
            className={styles.nodeToggle}
            aria-expanded={open}
            aria-controls={detailsId}
            aria-label={
              open ? `Hide details: ${item.module.title}` : `Why and what to do: ${item.module.title}`
            }
            onClick={(event) => {
              event.stopPropagation();
              setOpen(!open);
            }}
          >
            <ChevronDown size={16} aria-hidden />
          </button>
        </div>
        <Collapsible lazy collapsed={!open}>
          <SmoothHeight>
          <div className={styles.nodeBody} id={detailsId}>
            <p className={styles.nodeReason}>{reason}</p>
            {item.last_score && <p className={styles.muted}>Last checkpoint score: {item.last_score}</p>}
            {status === "failed" && <ReviewTopics topics={topicsToReview(item)} page={href} />}
            <ModuleTopics item={item} page={href} hasCheckpoint={hasCheckpoint} passed={status === "finished"} />
            {item.choice === "prove" &&
              (hasCheckpoint ? (
                <p className={styles.proveHow}>
                  <CircleCheck size={15} aria-hidden /> Prove it by passing the checkpoint at the end of the
                  module.
                </p>
              ) : (
                <Disclosure
                  className={styles.checklist}
                  summary={
                    <span className={styles.proveHow}>
                      <ListChecks size={15} aria-hidden /> Prove it with the module's checklist
                    </span>
                  }
                >
                  <p className={styles.muted}>
                    If you can already do all of this, mark the module done; if not, study it.
                  </p>
                  <ul>
                    {item.module.checklist.map((line) => (
                      <li key={line}>
                        <InlineMarkdown text={line} />
                      </li>
                    ))}
                  </ul>
                </Disclosure>
              ))}
            <div className={styles.nodeActions}>
              {/* A finished module's decision no longer changes: no switch for it. */}
              {status !== "finished" && (
              <div
                className={styles.segmented}
                role="radiogroup"
                aria-label={`${item.module.title}: what to do`}
              >
                {choices.map((choice) => (
                  <button
                    key={choice}
                    type="button"
                    role="radio"
                    aria-checked={item.choice === choice}
                    data-choice={choice}
                    disabled={busy}
                    title={CHOICE_HINT[choice]}
                    onClick={() => onChoose(choice)}
                  >
                    {CHOICE_LABEL[choice]}
                  </button>
                ))}
              </div>
              )}
              {href && (
                <Link to={href} className={styles.ghostSm}>
                  Open <ArrowRight size={14} aria-hidden />
                </Link>
              )}
            </div>
          </div>
          </SmoothHeight>
        </Collapsible>
      </div>
    </li>
  );
}

// The stops of a stage. A stage skipped as a whole starts folded under its milestone; one the learner empties
// while looking at it stays open, and the tree is the same either way, so no stop is remounted (and closed)
// by a change of choice.
function StageStops({ skipped, children }: { skipped: boolean; children: ReactNode }): ReactNode {
  const [open, setOpen] = useState(!skipped);
  return (
    <div className={skipped ? styles.stageSkipped : undefined} data-open={open}>
      {skipped && (
        <button type="button" className={styles.disclosure} aria-expanded={open} onClick={() => setOpen(!open)}>
          <span>{open ? "Hide the skipped modules" : "Show the skipped modules"}</span>
          <ChevronDown size={16} aria-hidden />
        </button>
      )}
      <Collapsible lazy collapsed={skipped && !open}>
        <ol className={styles.nodes}>{children}</ol>
      </Collapsible>
    </div>
  );
}


function Proposals({
  api,
  path,
  onError,
}: {
  api: PathApi;
  path: LearningPath;
  onError: (text: string) => void;
}): ReactNode {
  const proposals = path.proposals ?? [];
  if (!proposals.length)
    return path.suggestions_pending ? (
      <div className={styles.banner} data-tone="info">
        <Spinner />
        <div>
          <strong>Checking the rest of your path</strong>
          <p>Your result is saved. Suggestions for the modules that follow will appear here in a few minutes.</p>
        </div>
      </div>
    ) : null;
  const titleOf = (id: string) => path.items.find((item) => item.module.id === id)?.module.title ?? id;
  const failed = proposals.some((proposal) => proposal.after_failure);
  async function answer(action: "accept" | "decline", proposal: Proposal) {
    try {
      setPath(await api.act(action, proposal.module_id, proposal.topic));
    } catch (reason) {
      if (!handleSignedOut(reason)) onError(message(reason));
    }
  }
  return (
    <div className={styles.banner} data-tone={failed ? "warn" : "info"}>
      <Sparkles size={20} aria-hidden />
      <div>
        <strong>{failed ? "The checkpoint showed gaps" : "You passed a checkpoint without a mistake"}</strong>
        <p>
          {failed
            ? "These later parts build on the topics you got wrong and may need more of your time."
            : "These modules may need less of your time."}{" "}
          Nothing changes unless you accept.
        </p>
        <ul className={styles.proposalList}>
          {proposals.map((proposal) => (
            <li key={`${proposal.module_id}#${proposal.topic ?? ""}`}>
              <span>
                <strong>{titleOf(proposal.module_id)}</strong> →{" "}
                {proposal.topic ? (
                  <strong>{proposalAction(proposal)}</strong>
                ) : (
                  proposal.choice && <ChoiceChip choice={proposal.choice} />
                )}{" "}
                {proposal.reason}
              </span>
              <span className={styles.actions}>
                <button type="button" className={styles.primarySm} onClick={() => void answer("accept", proposal)}>
                  Accept
                </button>
                <button type="button" className={styles.ghostSm} onClick={() => void answer("decline", proposal)}>
                  Keep as is
                </button>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PublicLinkCard({ api }: { api: PathApi }): ReactNode {
  const page = useBaseUrl("/progress");
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    api.publicLink().then(setToken, (reason) => setError(message(reason)));
  }, [api]);
  // `page` is the course site's page, also when the panel is embedded in another site.
  const link = token ? new URL(`${page}?link=${encodeURIComponent(token)}`, window.location.origin).href : null;
  const act = async (action: () => Promise<string | void>) => {
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const result = await action();
      setToken(typeof result === "string" ? result : null);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={styles.card}>
      <h3>
        <Link2 size={16} aria-hidden /> Public link to your progress
      </h3>
      <p className={styles.muted}>
        A page anyone with the link can open: your path's goal and level, and the modules you finished, with
        checkpoint scores and accepted projects. Never your email or your answers.
      </p>
      {link ? (
        <>
          <input
            className={styles.linkField}
            readOnly
            value={link}
            aria-label="Your public link"
            onFocus={(event) => event.target.select()}
          />
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.ghostSm}
              disabled={busy}
              onClick={() => void navigator.clipboard.writeText(link).then(() => setCopied(true))}
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <a className={styles.ghostSm} href={link} target="_blank" rel="noreferrer">
              Open
            </a>
            <button
              type="button"
              className={styles.ghostSm}
              disabled={busy}
              onClick={() => void act(() => api.newPublicLink())}
            >
              New link
            </button>
            <button
              type="button"
              className={styles.dangerButton}
              disabled={busy}
              onClick={() => void act(() => api.removePublicLink())}
            >
              Remove
            </button>
          </div>
          <p className={styles.muted}>A new link, or removing this one, stops this link from working.</p>
        </>
      ) : (
        <button
          type="button"
          className={styles.ghostSm}
          disabled={busy || token === undefined}
          onClick={() => void act(() => api.newPublicLink())}
        >
          {busy && <Spinner />} Make a link
        </button>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}

function Settings({
  api,
  path,
  busy,
  run,
}: {
  api: PathApi;
  path: LearningPath;
  busy: string | null;
  run: (label: string, action: () => Promise<LearningPath | void>) => Promise<boolean>;
}): ReactNode {
  const [goal, setGoal] = useState("");
  const [resetting, setResetting] = useState(false);
  return (
    <div className={styles.settings}>
      <form
        className={styles.card}
        onSubmit={(event) => {
          event.preventDefault();
          void run("goal", () => api.changeGoal(goal)).then((ok) => ok && setGoal(""));
        }}
      >
        <h3>
          <Target size={16} aria-hidden /> Change your goal
        </h3>
        <p className={styles.muted}>
          The rest of your path is planned again for the new goal. Modules you have started keep their
          decision and progress; you confirm the new path again.
        </p>
        <textarea
          rows={2}
          value={goal}
          maxLength={2000}
          aria-label="Your new goal"
          onChange={(event) => setGoal(event.target.value)}
        />
        <button type="submit" className={styles.ghostSm} disabled={goal.trim().length < 3 || busy !== null}>
          {busy === "goal" && <Spinner />} {busy === "goal" ? "Planning…" : "Plan for this goal"}
        </button>
      </form>

      <PublicLinkCard api={api} />

      <div className={styles.card}>
        <h3>
          <RotateCcw size={16} aria-hidden /> Start over
        </h3>
        <p className={styles.muted}>Answer the questions again and plan a new path. Your progress is lost.</p>
        {resetting ? (
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.dangerButton}
              onClick={() =>
                void run("reset", async () => {
                  await api.reset();
                  setPath(null);
                })
              }
            >
              Delete this path
            </button>
            <button type="button" className={styles.ghostSm} onClick={() => setResetting(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" className={styles.ghostSm} onClick={() => setResetting(true)}>
            Start over
          </button>
        )}
      </div>
    </div>
  );
}

// A section that opens and closes. A button, not <details>, so the site's own styling of <details> stays out.
function Disclosure({
  summary,
  className,
  children,
}: {
  summary: ReactNode;
  className?: string;
  children: ReactNode;
}): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <div className={className} data-open={open}>
      <button type="button" className={styles.disclosure} aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{summary}</span>
        <ChevronDown size={16} aria-hidden />
      </button>
      {open && children}
    </div>
  );
}
