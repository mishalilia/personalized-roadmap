import React, { useEffect, useState, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import { useDoc, useDocsVersion } from "@docusaurus/plugin-content-docs/client";
import { ApiError, usePathApi } from "./api";
import Checkpoint from "./Checkpoint";
import CodingProblem from "./CodingProblem";
import { ProgressLine } from "./ProgressLine";
import {
  isLocked,
  progressOf,
  type CheckpointSummary,
  type Choice,
  type LearningPath,
  type PathItem,
} from "./model";
import { useModulePages, useVersionLabel } from "./useModulePages";
import { useSavedPath } from "./useSavedPath";
import styles from "./PersonalPath.module.css";

const HEADLINE: Record<Choice, string> = {
  study: "Your path: study this module",
  prove: "Your path: prove this module",
  skip: "Your path: you can skip this module",
};

// What the learner's confirmed path says about the module on this page, and their progress in it: the
// checkpoint, or marking it done. Shown only in the browser, since the path lives there.
export default function PathBadge(): ReactNode {
  const { metadata } = useDoc();
  const version = useDocsVersion();
  const api = usePathApi();
  const [saved, update] = useSavedPath();
  const [checkpoints, setCheckpoints] = useState<Record<string, CheckpointSummary>>({});
  // The attempt the learner is taking; it stays on screen with its result until they close it.
  const [taking, setTaking] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Keeps the solved problem and its result on screen after the module turns "passed".
  const [solvedNow, setSolvedNow] = useState(false);

  const siteVersion = saved?.path.curriculum_site_version ?? saved?.siteVersion ?? null;
  const pageOf = useModulePages(siteVersion);
  const versionLabel = useVersionLabel(siteVersion);
  const path = saved?.path;
  const item = path?.confirmed_at
    ? path.items.find((candidate) => candidate.module.id === metadata.id)
    : undefined;

  useEffect(() => {
    if (item && api && path)
      api.checkpoints(path.curriculum_version).then(setCheckpoints).catch(() => setCheckpoints({}));
  }, [item?.module.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!path || !item) return null;

  // The path was planned for another version of this page, whose content may differ.
  if (version.version !== siteVersion) {
    const page = pageOf(item.module.id);
    return page ? (
      <aside data-personal-path className={styles.badge} data-choice="other">
        Your personal path covers this module in the {versionLabel ?? siteVersion} curriculum.{" "}
        <Link to={page}>Open that version</Link> to see your decision.
      </aside>
    ) : null;
  }

  async function act(action: "done" | "accept" | "decline") {
    if (!api || !path || !item) return;
    setError(null);
    try {
      update(await api.act(action, path, item.module.id));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Something went wrong.");
    }
  }

  const proposal = path.proposals?.find((p) => p.module_id === item.module.id);
  const blocking = path.items.find((i) => i.module.id === path.blocking_module_id);
  const hasCheckpoint = item.module.id in checkpoints;
  const progress = progressOf(item);

  return (
    <aside data-personal-path className={styles.badge} data-choice={item.choice}>
      <strong>{HEADLINE[item.choice]}</strong>
      <span>{explanation(item)}</span>

      {item.choice !== "skip" && isLocked(path, item.module.id) && blocking && (
        <span className={styles.locked}>
          🔒 Locked until you pass the checkpoint of{" "}
          <Link to={pageOf(blocking.module.id) ?? "/personal-path"}>{blocking.module.title}</Link>.
        </span>
      )}

      {item.choice !== "skip" && !isLocked(path, item.module.id) && (
        <>
          <ProgressLine item={item} />
          {taking !== null && api ? (
            <>
              <Checkpoint
                key={taking}
                api={api}
                path={path}
                moduleId={item.module.id}
                attempt={taking}
                onResult={(next: LearningPath) => update(next)}
              />
              <button type="button" className="button button--link button--sm" onClick={() => setTaking(null)}>
                Close the checkpoint
              </button>
            </>
          ) : (
            hasCheckpoint &&
            progress !== "passed" &&
            progress !== "practice" &&
            api && (
              <button
                type="button"
                className="button button--primary button--sm"
                onClick={() => setTaking(item.attempts ?? 0)}
              >
                {progress === "failed" ? "Try the checkpoint again" : "Take the checkpoint"}
              </button>
            )
          )}
          {(progress === "practice" || solvedNow) && api && (
            <CodingProblem
              api={api}
              path={path}
              moduleId={item.module.id}
              onSolved={(next: LearningPath) => {
                setSolvedNow(true);
                update(next);
              }}
            />
          )}
          {!hasCheckpoint && progress === "not_started" && api && (
            <button type="button" className="button button--outline button--primary button--sm" onClick={() => void act("done")}>
              Mark as done
            </button>
          )}
        </>
      )}

      {proposal && (
        <span className={styles.proposal}>
          Suggested after your last checkpoint: <strong>{proposal.choice}</strong> it. {proposal.reason}{" "}
          <button type="button" className="button button--link button--sm" onClick={() => void act("accept")}>
            Accept
          </button>
          <button type="button" className="button button--link button--sm" onClick={() => void act("decline")}>
            Decline
          </button>
        </span>
      )}
      {error && <span className={styles.error}>{error}</span>}
      <Link to="/personal-path">Your whole path</Link>
    </aside>
  );
}

function explanation(item: PathItem): string {
  if (item.adjustment) return item.adjustment;
  if (item.choice !== item.suggested)
    return `Your own choice; the planner suggested to ${item.suggested} it.`;
  return item.choice === "prove"
    ? `${item.reason} Pass the checkpoint to prove it; if you cannot, study the module.`
    : item.reason;
}
