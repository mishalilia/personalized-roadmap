import React, { type ReactNode } from "react";
import { progressOf, type PathItem } from "./model";
import styles from "./PersonalPath.module.css";

// Where the learner is with a module: checkpoint passed or not yet, or marked done.
export function ProgressLine({ item }: { item: PathItem }): ReactNode {
  const progress = progressOf(item);
  if (progress === "passed") return <span className={styles.passed}>✓ Checkpoint passed ({item.last_score})</span>;
  if (progress === "practice")
    return (
      <span className={styles.locked}>
        Questions passed ({item.last_score}); the coding problem is next
      </span>
    );
  if (progress === "done") return <span className={styles.passed}>✓ Done</span>;
  if (progress === "failed")
    return (
      <span className={styles.failedText}>
        Checkpoint not passed yet ({item.last_score}, {item.attempts} attempt
        {item.attempts === 1 ? "" : "s"})
      </span>
    );
  return null;
}
