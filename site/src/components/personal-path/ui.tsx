// Small pieces every view of the path shares, so a module looks the same in the sidebar, on its page and
// on the path page.
import Link from "@docusaurus/Link";
import React, { useEffect, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { Check, Lock, SkipForward } from "lucide-react";
import type { Choice, Status } from "./model";
import styles from "./path.module.css";

export const CHOICE_LABEL: Record<Choice, string> = {
  study: "Study",
  prove: "Prove",
  skip: "Skip",
};

export const CHOICE_HINT: Record<Choice, string> = {
  study: "Work through the module.",
  prove: "Show you know it with its checklist and checkpoint; study it only if you cannot.",
  skip: "Leave it out of your path.",
};

export const STATUS_LABEL: Record<Status, string> = {
  skipped: "Skipped",
  locked: "Locked",
  finished: "Completed",
  practice: "Coding problem left",
  failed: "Checkpoint not passed yet",
  submitted: "Waiting for review",
  returned: "Changes requested",
  next: "Up next",
  todo: "Not started",
};

export function ChoiceChip({ choice, className }: { choice: Choice; className?: string }): ReactNode {
  return (
    <span className={clsx(styles.chip, className)} data-choice={choice}>
      {CHOICE_LABEL[choice]}
    </span>
  );
}

export function StatusIcon({ status, size = 18 }: { status: Status; size?: number }): ReactNode {
  return (
    <span
      className={styles.statusIcon}
      data-status={status}
      style={{ width: size, height: size }}
      role="img"
      aria-label={STATUS_LABEL[status]}
      title={STATUS_LABEL[status]}
    >
      {status === "finished" && <Check size={size * 0.62} strokeWidth={3} />}
      {status === "locked" && <Lock size={size * 0.62} strokeWidth={2.5} />}
      {status === "skipped" && <SkipForward size={size * 0.8} strokeWidth={2.5} fill="currentColor" />}
      {(status === "failed" || status === "returned") && <span aria-hidden>!</span>}
    </span>
  );
}

export function ProgressRing({
  finished,
  total,
  size = 44,
  label = true,
}: {
  finished: number;
  total: number;
  size?: number;
  label?: boolean;
}): ReactNode {
  const stroke = Math.max(3, size / 11);
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const share = total ? finished / total : 0;
  return (
    <span
      className={styles.ring}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${finished} of ${total} modules completed`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle className={styles.ringTrack} cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
        <circle
          className={styles.ringValue}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - share)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {label && (
        <span className={styles.ringLabel} style={{ fontSize: size / 3.6 }}>
          {Math.round(share * 100)}%
        </span>
      )}
    </span>
  );
}

export function ProgressBar({ finished, total }: { finished: number; total: number }): ReactNode {
  return (
    <span
      className={styles.bar}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={finished}
      aria-label="Modules completed"
    >
      <span style={{ width: `${total ? (finished / total) * 100 : 0}%` }} />
    </span>
  );
}

export function Spinner(): ReactNode {
  return <span className={styles.spinner} aria-hidden />;
}

// After a failed checkpoint: the topics of the wrong answers, each a link to its section of the module page.
// `page` is that page's address, or nothing for links on the page itself.
export function ReviewTopics({
  topics,
  page,
  lead = "Review",
}: {
  topics: { title: string; anchor: string }[];
  page?: string;
  lead?: string;
}): ReactNode {
  if (topics.length === 0) return null;
  return (
    <p className={styles.reviewTopics}>
      {lead}:{" "}
      {topics.map((topic, index) => (
        <React.Fragment key={topic.anchor}>
          {index > 0 && ", "}
          {page ? (
            <Link to={`${page}#${topic.anchor}`}>{topic.title}</Link>
          ) : (
            <a href={`#${topic.anchor}`}>{topic.title}</a>
          )}
        </React.Fragment>
      ))}
    </p>
  );
}

// Eases from the old height to the new one when what is inside changes size, instead of jumping.
export function SmoothHeight({ children }: { children: ReactNode }): ReactNode {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = outer.current;
    const content = inner.current;
    if (!box || !content || typeof ResizeObserver === "undefined") return;
    let last = content.offsetHeight;
    const settle = () => {
      box.style.height = "";
      box.style.overflow = "";
    };
    // Called after layout and before paint, so the old height is put back before the jump is ever seen.
    const observer = new ResizeObserver(() => {
      const next = content.offsetHeight;
      if (next === last) return;
      const from = box.style.height ? box.getBoundingClientRect().height : last;
      last = next;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return settle();
      box.style.overflow = "hidden";
      box.style.height = `${from}px`;
      void box.offsetHeight;
      box.style.height = `${next}px`;
    });
    const onEnd = (event: TransitionEvent) => {
      if (event.target === box && event.propertyName === "height") settle();
    };
    observer.observe(content);
    box.addEventListener("transitionend", onEnd);
    return () => {
      observer.disconnect();
      box.removeEventListener("transitionend", onEnd);
    };
  }, []);
  return (
    <div ref={outer} className={styles.smoothHeight}>
      <div ref={inner}>{children}</div>
    </div>
  );
}

// Shows or hides what it holds by opening and closing room for it, fading as it goes, both ways: on the way out
// it keeps showing what it held until it has closed.
export function Reveal({ show, children }: { show: boolean; children: ReactNode }): ReactNode {
  const held = useRef<ReactNode>(children);
  if (show) held.current = children;
  const [mounted, setMounted] = useState(show);
  const [open, setOpen] = useState(show);
  useEffect(() => {
    if (show) {
      setMounted(true);
      // Mounted closed first, then opened on the next frame, so the opening plays.
      const frame = requestAnimationFrame(() => requestAnimationFrame(() => setOpen(true)));
      return () => cancelAnimationFrame(frame);
    }
    setOpen(false);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setMounted(false);
    return undefined;
  }, [show]);
  if (!mounted) return null;
  return (
    <div
      className={styles.reveal}
      data-open={open}
      onTransitionEnd={(event) => {
        if (event.target === event.currentTarget && !show) setMounted(false);
      }}
    >
      <div className={styles.revealInner}>{held.current}</div>
    </div>
  );
}
