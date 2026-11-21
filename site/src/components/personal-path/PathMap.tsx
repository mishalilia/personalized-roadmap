// The learner's path as a map over the whole screen: the course's modules on one road, section by section, with
// each module's topics branching off it. Everything on it opens the page it names. The panel is for working
// through the path next to a module; the map is for seeing all of it at once.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import {
  ArrowRight,
  BookOpen,
  CircleCheck,
  FastForward,
  Map as MapIcon,
  SkipForward,
  TriangleAlert,
  X,
} from "lucide-react";
import { message, usePathApi } from "./api";
import {
  bySection,
  canBeProved,
  headingAnchor,
  isIncluded,
  statusOf,
  type Choice,
  type LearningPath,
  type PathItem,
  type Status,
  topicChoiceOf,
  type TopicChoice,
  CHECKPOINT_ANCHOR,
  allTopicsFinished,
} from "./model";
import { handleSignedOut, openAuth, setPath, useCheckpoints, usePathState } from "./store";
import { useModulePages } from "./useModulePages";
import {
  CHOICE_HINT,
  CHOICE_LABEL,
  ChoiceChip,
  Reveal,
  SmoothHeight,
  STATUS_LABEL,
  Spinner,
  StatusIcon,
} from "./ui";
import styles from "./map.module.css";

// What the card beside a stop or a topic shows: the module it belongs to, and where to put the card.
interface Peek {
  moduleId: string;
  topic: string | null;
  rect: DOMRect;
}

// Headings that describe the page rather than something to learn.
const NOT_TOPICS = /^(curriculum|capstone( project)?|resources)$/i;

const plain = (title: string) => title.replace(/^\d+\.\s*/, "");

// The topics a module's stop branches into. A capstone's headings are the project brief, not topics.
function topicsOf(item: PathItem): { title: string; anchor: string }[] {
  if (item.module.is_project) return [];
  return (item.module.topics ?? [])
    .filter((topic) => !NOT_TOPICS.test(plain(topic.title)))
    .map((topic) => ({
      title: plain(topic.title),
      anchor: topic.anchor ?? headingAnchor(topic.title),
    }));
}

const isElectives = (item: PathItem) => item.module.id.endsWith("/electives");

export function MapButton({ onOpen }: { onOpen: () => void }): ReactNode {
  return (
    <button type="button" className={styles.mapButton} onClick={onOpen} title="See your whole path as a map">
      <MapIcon size={15} aria-hidden /> Map
    </button>
  );
}

export default function PathMap({ path, onClose }: { path: LearningPath; onClose: () => void }): ReactNode {
  const pageOf = useModulePages(path.curriculum_site_version ?? null);
  const sections = bySection(path.items);
  const canvas = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [lines, setLines] = useState<{ d: string; kind: string }[]>([]);
  const [size, setSize] = useState({ width: 0, height: 0 });
  // The map leaves the way it came: the overlay plays its exit and is removed when it ends.
  const [closing, setClosing] = useState(false);
  const close = useCallback(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) onClose();
    else setClosing(true);
  }, [onClose]);

  const [peek, setPeek] = useState<Peek | null>(null);
  const hideTimer = useRef<number | undefined>(undefined);
  const show = (moduleId: string, topic: string | null, element: Element) => {
    window.clearTimeout(hideTimer.current);
    setPeek({ moduleId, topic, rect: element.getBoundingClientRect() });
  };
  const hide = () => {
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setPeek(null), 180);
  };
  const keep = () => window.clearTimeout(hideTimer.current);
  useEffect(() => () => window.clearTimeout(hideTimer.current), []);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [close]);

  // The road and the branches are drawn over the laid-out stops, so they follow wherever the layout puts them.
  useLayoutEffect(() => {
    const root = canvas.current;
    if (!root) return;
    const draw = () => {
      const narrow = window.matchMedia("(max-width: 760px)").matches;
      const origin = root.getBoundingClientRect();
      const box = (element: Element) => {
        const rect = element.getBoundingClientRect();
        return {
          left: rect.left - origin.left,
          right: rect.right - origin.left,
          top: rect.top - origin.top,
          bottom: rect.bottom - origin.top,
          x: rect.left - origin.left + rect.width / 2,
          y: rect.top - origin.top + rect.height / 2,
        };
      };
      const drawn: { d: string; kind: string }[] = [];
      const stops = Array.from(root.querySelectorAll<HTMLElement>("[data-road]"));
      for (let index = 1; index < stops.length; index++) {
        const from = box(stops[index - 1]);
        const to = box(stops[index]);
        const finished =
          stops[index - 1].dataset.road === "finished" && stops[index].dataset.road === "finished";
        drawn.push({
          // On a narrow screen the road runs down the left edge, clear of the topics under each stop.
          d: narrow
            ? `M ${from.left - 14} ${from.y} L ${to.left - 14} ${to.y}`
            : `M ${from.x} ${from.bottom} L ${to.x} ${to.top}`,
          kind: finished ? "roadDone" : "road",
        });
      }
      for (const branch of Array.from(root.querySelectorAll<HTMLElement>("[data-branch-of]"))) {
        const stop = root.querySelector(`[data-stop="${CSS.escape(branch.dataset.branchOf ?? "")}"]`);
        if (!stop) continue;
        const from = box(stop);
        const to = box(branch);
        const kind = branch.dataset.dim === "true" ? "branchDim" : "branch";
        if (to.right <= from.left) {
          const middle = (to.right + from.left) / 2;
          drawn.push({
            d: `M ${from.left} ${from.y} C ${middle} ${from.y}, ${middle} ${to.y}, ${to.right} ${to.y}`,
            kind,
          });
        } else if (to.left >= from.right) {
          const middle = (from.right + to.left) / 2;
          drawn.push({
            d: `M ${from.right} ${from.y} C ${middle} ${from.y}, ${middle} ${to.y}, ${to.left} ${to.y}`,
            kind,
          });
        }
      }
      setLines(drawn);
      setSize({ width: root.scrollWidth, height: root.scrollHeight });
    };
    draw();
    // A block that changes size, as when the web fonts arrive, moves what the lines join.
    let frame = 0;
    const redraw = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    };
    const observer = new ResizeObserver(redraw);
    observer.observe(root);
    root.querySelectorAll("[data-road], [data-branch-of]").forEach((element) => observer.observe(element));
    void document.fonts?.ready.then(redraw);
    // The map opens with a slight zoom, which measuring during it would shrink the lines by.
    const overlay = root.closest("[role=dialog]");
    overlay?.addEventListener("animationend", redraw);
    return () => {
      overlay?.removeEventListener("animationend", redraw);
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [path]);

  return (
    <div
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label="Your path as a map"
      data-closing={closing}
      onAnimationEnd={(event) => {
        if (closing && event.target === event.currentTarget) onClose();
      }}
    >
      <header className={styles.bar}>
        <div className={styles.barTitle}>
          <strong>Your path</strong>
          {(path.title ?? path.answers?.goal) && <span>{path.title ?? path.answers?.goal}</span>}
        </div>
        <ul className={styles.legend} aria-label="What the colours mean">
          <li data-choice="study">Study</li>
          <li data-choice="prove">Prove</li>
          <li data-choice="skip">Skip</li>
          <li data-status="finished">Done</li>
          <li data-topic="study">
            <BookOpen size={13} aria-hidden /> Read
          </li>
          <li data-topic="skim">
            <FastForward size={13} aria-hidden /> Skim
          </li>
          <li data-topic="skip">
            <SkipForward size={13} aria-hidden /> Skip
          </li>
        </ul>
        <button ref={closeButton} type="button" className={styles.close} onClick={close}>
          <X size={16} aria-hidden /> Close map
        </button>
      </header>
      <div
        className={styles.scroller}
        onScroll={() => setPeek(null)}
        onPointerDown={(event) => {
          // A tap or click on the map's background puts the card away.
          if (!(event.target as Element).closest("[data-stop], [data-branch-of]")) setPeek(null);
        }}
      >
        <div className={styles.canvas} ref={canvas}>
          <svg className={styles.lines} width={size.width} height={size.height} aria-hidden>
            {lines.map((line, index) => (
              <path key={index} d={line.d} className={styles[line.kind]} />
            ))}
          </svg>
          {sections.map(({ section, items }) => {
            const parts = section.split(" › ");
            const name = parts.pop();
            const kept = items.filter(isIncluded).length;
            return (
              <section key={section} className={styles.stage} data-skipped={kept === 0}>
                <div className={styles.milestone} data-road={kept === 0 ? "skipped" : "stage"}>
                  {parts.length > 0 && <small>{parts.join(" › ")}</small>}
                  <h2>{name}</h2>
                </div>
                {items.map((item) => (
                  <Stop
                    key={item.module.id}
                    item={item}
                    status={statusOf(path, item)}
                    confirmed={path.confirmed_at !== null}
                    href={pageOf(item.module.id)}
                    onFollow={close}
                    onShow={show}
                    onHide={hide}
                  />
                ))}
              </section>
            );
          })}
        </div>
      </div>
      {peek && (
        <PeekCard
          key={`${peek.moduleId}|${peek.topic ?? ""}`}
          path={path}
          peek={peek}
          href={pageOf(peek.moduleId)}
          onEnter={keep}
          onLeave={hide}
          onFollow={close}
        />
      )}
    </div>
  );
}

// Why the path has a module the way it is, and the switch to change it, beside the stop or topic under the pointer.
const TOPIC_LABEL: Record<TopicChoice, string> = { study: "Study", skim: "Skim", skip: "Skip" };
const TOPIC_HINT: Record<TopicChoice, string> = {
  study: "Read it in full",
  skim: "Go through it quickly; the checkpoint still asks about it",
  skip: "You know it: leave it out, and the checkpoint does not ask about it",
};

function PeekCard({
  path,
  peek,
  href,
  onEnter,
  onLeave,
  onFollow,
}: {
  path: LearningPath;
  peek: Peek;
  href: string | undefined;
  onEnter: () => void;
  onLeave: () => void;
  onFollow: () => void;
}): ReactNode {
  const api = usePathApi();
  const { account } = usePathState();
  const checkpoints = useCheckpoints(api, path.curriculum_version);
  const hovered = useRef(false);
  const card = useRef<HTMLDivElement>(null);
  // After a change the card's text may shrink and leave the pointer outside it without the pointer moving.
  // The browser reports that as leaving the card; the card then closes only once the pointer really moves
  // outside it. `lastMove` is where the pointer last moved to.
  const lastMove = useRef<{ x: number; y: number } | null>(null);
  const pendingLeave = useRef<((event: MouseEvent) => void) | null>(null);
  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      lastMove.current = { x: event.clientX, y: event.clientY };
    };
    document.addEventListener("mousemove", onMove, true);
    return () => {
      document.removeEventListener("mousemove", onMove, true);
      if (pendingLeave.current) document.removeEventListener("mousemove", pendingLeave.current, true);
    };
  }, []);
  const leaveCard = (event: React.MouseEvent) => {
    hovered.current = false;
    const at = lastMove.current;
    if (at && at.x === event.clientX && at.y === event.clientY) {
      const onNextMove = (move: MouseEvent) => {
        document.removeEventListener("mousemove", onNextMove, true);
        pendingLeave.current = null;
        if (!card.current?.contains(move.target as Node)) onLeave();
      };
      if (pendingLeave.current) document.removeEventListener("mousemove", pendingLeave.current, true);
      pendingLeave.current = onNextMove;
      document.addEventListener("mousemove", onNextMove, true);
      return;
    }
    onLeave();
  };
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const item = path.items.find((candidate) => candidate.module.id === peek.moduleId);
  if (!item) return null;
  const status = statusOf(path, item);
  // A topic under the pointer: the module's own topic, what it teaches, and what the path says about it.
  const bare = (title: string) => title.replace(/^\d+\.\s*/, "");
  const topic = peek.topic ? item.module.topics?.find((candidate) => bare(candidate.title) === peek.topic) : undefined;
  const skim = topic && item.choice === "study" ? item.skim?.find((s) => bare(s.topic) === peek.topic) : undefined;
  const skip = topic && item.choice === "study" ? item.skip_topics?.find((s) => bare(s.topic) === peek.topic) : undefined;
  const topicChoice: TopicChoice = skip ? "skip" : skim ? "skim" : "study";
  // As in the path panel: topics to review are marked until the module is finished, not after a pass.
  const missed =
    topic && status !== "finished" && (item.missed_topics ?? []).some((name) => bare(name) === peek.topic);
  const done = Boolean(topic) && (item.finished_topics ?? []).some((name) => bare(name) === peek.topic);
  // As in the path panel: a topic of a module the learner studies, on a confirmed path, until the module is done.
  const canFinish =
    Boolean(topic) &&
    Boolean(path.confirmed_at) &&
    item.choice === "study" &&
    !item.module.is_project &&
    topicChoice !== "skip" &&
    status !== "finished" &&
    status !== "locked";
  const choices: Choice[] = canBeProved(item) ? ["study", "prove", "skip"] : ["study", "skip"];
  const reason =
    item.adjustment ??
    (item.choice === item.suggested
      ? item.reason
      : `Your own choice. The planner suggested to ${item.suggested} it: ${item.reason}`);

  // Changing a module here is the learner's own approval, as on its page: a confirmed path stays confirmed.
  async function choose(choice: Choice) {
    if (!api || choice === item!.choice) return;
    if (!account) return openAuth("sign-up", "Create an account to change and keep your path.");
    setBusy(true);
    setError(null);
    try {
      const changed = await api.choose(item!.module.id, choice);
      setPath(path.confirmed_at ? await api.confirm() : changed);
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  // A topic of a module the learner studies: read it in full, skim it, or skip it out of the checkpoint. The
  // learner decides it here, so the path stays confirmed.
  async function chooseTopic(title: string, choice: TopicChoice) {
    if (!api || choice === topicChoice) return;
    if (!account) return openAuth("sign-up", "Create an account to change and keep your path.");
    setBusy(true);
    setError(null);
    try {
      setPath(await api.chooseTopic(item!.module.id, title, choice));
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function finishTopic(title: string, finished: boolean) {
    if (!api) return;
    setBusy(true);
    setError(null);
    try {
      setPath(await api.finishTopic(item!.module.id, title, finished));
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  // Beside the element where there is room, else under it (or above it near the bottom), inside the window.
  const width = Math.min(340, window.innerWidth - 24);
  let left: number;
  let top: number;
  if (window.innerWidth - peek.rect.right > width + 24) {
    left = peek.rect.right + 12;
    top = peek.rect.top - 8;
  } else if (peek.rect.left > width + 24) {
    left = peek.rect.left - width - 12;
    top = peek.rect.top - 8;
  } else {
    left = Math.min(Math.max(12, peek.rect.left), window.innerWidth - width - 12);
    top = peek.rect.bottom + 260 < window.innerHeight ? peek.rect.bottom + 8 : peek.rect.top - 268;
  }
  top = Math.min(Math.max(12, top), window.innerHeight - 280);

  return (
    <div
      ref={card}
      className={styles.peek}
      style={{ left, top, width }}
      role="dialog"
      aria-label={`${item.module.title}: why and what to do`}
      onMouseEnter={() => {
        hovered.current = true;
        onEnter();
      }}
      onMouseLeave={leaveCard}
      onFocus={onEnter}
      onBlur={(event) => {
        // A control disabled while the change is saved loses focus; that is not leaving the card.
        if (!hovered.current && !event.currentTarget.contains(event.relatedTarget as Node | null)) onLeave();
      }}
    >
      <SmoothHeight>
      {topic ? (
        <>
          <div className={styles.peekHead}>
            <strong>{peek.topic}</strong>
          </div>
          <p className={styles.peekTopic}>A topic of {item.module.title}</p>
          {topic.outcomes.length > 0 && (
            <ul className={styles.peekOutcomes}>
              {topic.outcomes.slice(0, 4).map((outcome) => (
                <li key={outcome}>{outcome}</li>
              ))}
            </ul>
          )}
          {skip && (
            <p className={styles.peekSkim}>
              {skip.chosen ? "You chose to skip it." : `You can skip it: ${skip.reason}`} The checkpoint leaves it
              out.
            </p>
          )}
          {skim && !skip && (
            <p className={styles.peekSkim}>
              {skim.chosen ? "You chose to skim it." : `You can skim it: ${skim.reason}`} The checkpoint still asks
              about it.
            </p>
          )}
          {missed && <p className={styles.peekMissed}>Your last checkpoint had a wrong answer here: review it.</p>}
          {!isIncluded(item) && <p className={styles.peekTopic}>Its module is skipped in your path.</p>}
          {canFinish && topic && (
            <label className={styles.peekDone}>
              <input
                type="checkbox"
                checked={done}
                disabled={busy}
                onChange={(event) => void finishTopic(topic.title, event.target.checked)}
              />
              I have finished this topic
            </label>
          )}
          <Reveal show={canFinish && allTopicsFinished(item)}>
            <p className={styles.peekAllDone}>
              Every topic of {item.module.title} is finished:{" "}
              {href ? (
                <Link to={`${href}#${CHECKPOINT_ANCHOR}`} onClick={onFollow}>
                  {item.module.id in checkpoints ? "time for its checkpoint" : "mark the module done"}
                </Link>
              ) : item.module.id in checkpoints ? (
                "time for its checkpoint."
              ) : (
                "mark the module done."
              )}
            </p>
          </Reveal>
          {/* The status is the module's: say so on the same line, not as if it were the topic's. */}
          <p className={styles.peekModuleLine}>
            The whole module: <ChoiceChip choice={item.choice} />
            {path.confirmed_at && status !== "skipped" && (
              <span className={styles.peekModuleStatus}>
                <StatusIcon status={status} size={14} /> {STATUS_LABEL[status]}
                {item.last_score && ` · last checkpoint ${item.last_score}`}
              </span>
            )}
          </p>
        </>
      ) : (
        <>
          <div className={styles.peekHead}>
            <ChoiceChip choice={item.choice} />
            <strong>{item.module.title}</strong>
          </div>
          <p className={styles.peekReason}>{reason}</p>
        </>
      )}
      {!topic && path.confirmed_at && status !== "skipped" && (
        <p className={styles.peekStatus}>
          <StatusIcon status={status} size={14} /> {STATUS_LABEL[status]}
          {item.last_score && ` · last checkpoint ${item.last_score}`}
        </p>
      )}
      <div className={styles.peekActions}>
        {topic ? (
          item.choice === "study" &&
          !item.module.is_project &&
          isIncluded(item) &&
          status !== "finished" && (
            <div className={styles.peekSwitch} role="radiogroup" aria-label={`${peek.topic}: how to read it`}>
              {(["study", "skim", "skip"] as const).map((choice) => (
                <button
                  key={choice}
                  type="button"
                  role="radio"
                  aria-checked={topicChoice === choice}
                  data-choice={choice}
                  disabled={busy}
                  title={TOPIC_HINT[choice]}
                  onClick={() => void chooseTopic(topic.title, choice)}
                >
                  {TOPIC_LABEL[choice]}
                </button>
              ))}
            </div>
          )
        ) : status === "finished" ? null : (
        <div className={styles.peekSwitch} role="radiogroup" aria-label={`${item.module.title}: what to do`}>
          {choices.map((choice) => (
            <button
              key={choice}
              type="button"
              role="radio"
              aria-checked={item.choice === choice}
              data-choice={choice}
              disabled={busy}
              title={CHOICE_HINT[choice]}
              onClick={() => void choose(choice)}
            >
              {CHOICE_LABEL[choice]}
            </button>
          ))}
        </div>
        )}
        {busy && <Spinner />}
        {href && (
          <Link
            to={topic ? `${href}#${topic.anchor ?? headingAnchor(topic.title)}` : href}
            className={styles.peekOpen}
            onClick={onFollow}
          >
            Open <ArrowRight size={14} aria-hidden />
          </Link>
        )}
      </div>
      {error && <p className={styles.peekError}>{error}</p>}
      </SmoothHeight>
    </div>
  );
}

function Stop({
  item,
  status,
  confirmed,
  href,
  onFollow,
  onShow,
  onHide,
}: {
  item: PathItem;
  status: Status;
  confirmed: boolean;
  href: string | undefined;
  onFollow: () => void;
  onShow: (moduleId: string, topic: string | null, element: Element) => void;
  onHide: () => void;
}): ReactNode {
  const topics = topicsOf(item);
  // Pointer events: Docusaurus's links take onMouseEnter for themselves, to prefetch the page. A mouse
  // shows the card on hover and a click opens the page; a tap, with no hover, shows the card instead,
  // whose Open link goes to the page.
  const tapped = useRef(false);
  const hover = (topic: string | null) => ({
    onPointerEnter: (event: React.PointerEvent) =>
      event.pointerType === "mouse" && onShow(item.module.id, topic, event.currentTarget),
    // A finger "leaves" as soon as it lifts; only a mouse moving away puts the card away.
    onPointerLeave: (event: React.PointerEvent) => event.pointerType === "mouse" && onHide(),
    onPointerDown: (event: React.PointerEvent) => {
      tapped.current = event.pointerType !== "mouse";
    },
    onClick: (event: React.MouseEvent) => {
      if (tapped.current) {
        event.preventDefault();
        tapped.current = false;
        onShow(item.module.id, topic, event.currentTarget);
      } else onFollow();
    },
    onFocus: (event: React.FocusEvent) => onShow(item.module.id, topic, event.currentTarget),
    onBlur: onHide,
  });
  const bare = (title: string) => title.replace(/^\d+\.\s*/, "");
  const half = Math.ceil(topics.length / 2);
  const sides = [topics.slice(0, half), topics.slice(half)];
  const dim = !isIncluded(item);
  const electives = isElectives(item);
  const label = (
    <>
      <StatusIcon status={confirmed || status === "skipped" ? status : "todo"} size={16} />
      <span className={styles.stopTitle}>{item.module.title}</span>
      <span className={styles.stopChoice}>
        {item.module.is_project ? "Project" : CHOICE_LABEL[item.choice]}
      </span>
    </>
  );
  return (
    <div className={styles.row}>
      {sides.map((side, index) => (
        <div key={index} className={index === 0 ? styles.left : styles.right}>
          {side.map((topic) => (
            <Topic
              key={topic.anchor}
              of={item.module.id}
              title={topic.title}
              href={href ? `${href}#${topic.anchor}` : undefined}
              dim={dim}
              option={electives}
              onFollow={onFollow}
              hover={hover(topic.title)}
              topicChoice={topicChoiceOf(item, topic.title)}
              done={
                (status === "finished" && topicChoiceOf(item, topic.title) !== "skip") ||
                (item.finished_topics ?? []).some((name) => bare(name) === bare(topic.title))
              }
              missed={
                status !== "finished" && (item.missed_topics ?? []).some((name) => bare(name) === bare(topic.title))
              }
              tone={item.module.is_project ? "project" : status === "finished" ? "finished" : item.choice}
            />
          ))}
        </div>
      ))}
      <div className={styles.center} data-road={status}>
        {href ? (
          <Link
            to={href}
            className={styles.stop}
            data-stop={item.module.id}
            data-choice={item.choice}
            data-status={status}
            {...hover(null)}
          >
            {label}
          </Link>
        ) : (
          <span
            className={styles.stop}
            data-stop={item.module.id}
            data-choice={item.choice}
            data-status={status}
            tabIndex={0}
            {...hover(null)}
          >
            {label}
          </span>
        )}
        {electives && topics.length > 0 && <span className={styles.note}>choose from the options</span>}
      </div>
    </div>
  );
}

function Topic({
  of,
  title,
  href,
  dim,
  option,
  onFollow,
  hover,
  topicChoice,
  missed,
  done = false,
  tone,
}: {
  of: string;
  title: string;
  href: string | undefined;
  dim: boolean;
  option: boolean;
  onFollow: () => void;
  hover: Record<string, unknown>;
  topicChoice: TopicChoice;
  missed: boolean;
  done?: boolean; // the learner marked it as finished
  tone: string;
}): ReactNode {
  // A mark before the title says how the learner takes the topic; a module's colour runs down its side.
  const Mark = missed
    ? TriangleAlert
    : done
      ? CircleCheck
      : topicChoice === "skim"
        ? FastForward
        : topicChoice === "skip"
          ? SkipForward
          : BookOpen;
  const content = (
    <>
      <Mark size={13} className={styles.topicMark} aria-hidden />
      <span className={styles.topicTitle}>{title}</span>
      {topicChoice !== "study" && !dim && <span className={styles.topicTag}>{topicChoice}</span>}
    </>
  );
  const props = {
    className: styles.topic,
    "data-tone": tone,
    "data-missed": missed,
    "data-done": done,
    "data-branch-of": of,
    "data-dim": dim,
    "data-option": option,
    "data-skim": topicChoice === "skim",
    "data-skip": topicChoice === "skip",
    ...hover,
  };
  return href ? (
    <Link to={href} {...props}>
      {content}
    </Link>
  ) : (
    <span {...props}>{content}</span>
  );
}
