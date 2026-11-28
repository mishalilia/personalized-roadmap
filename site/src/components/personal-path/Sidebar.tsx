// The path inside the course's own navigation: a card above the sidebar with the learner's progress and
// what to open next, and each module's status beside its name in the sidebar.
import React, { type ReactNode } from "react";
import Link from "@docusaurus/Link";
import { useActiveVersion } from "@docusaurus/plugin-content-docs/client";
import { ArrowRight, Route } from "lucide-react";
import { completion, nextUp, openHref, statusOf, type Status } from "./model";
import { setDrawer, usePathState } from "./store";
import { useModulePages } from "./useModulePages";
import { ProgressBar } from "./ui";
import styles from "./path.module.css";

// The learner's path, if it was planned for the curriculum version this page shows. The version comes from
// the route, not from the docs page's context: on small screens the sidebar renders in the navbar's menu,
// outside that context.
function usePathOfThisVersion() {
  const { path, ready } = usePathState();
  const version = useActiveVersion(undefined)?.name ?? null;
  const matches = path !== null && (path.curriculum_site_version ?? null) === version;
  return { path: matches ? path : null, otherVersion: path !== null && !matches, ready };
}

export function SidebarPathCard(): ReactNode {
  const { path, otherVersion, ready } = usePathOfThisVersion();
  const { path: anyPath } = usePathState();
  const pageOf = useModulePages(anyPath?.curriculum_site_version ?? null);
  if (!ready) return null;

  if (!path && !otherVersion)
    return (
      <button type="button" onClick={() => setDrawer(true)} className={styles.sideCard} data-kind="cta">
        <Route size={18} aria-hidden />
        <span>
          <strong>Get a personal path</strong>
          <small>A few questions about you; then see what to study, prove or skip.</small>
        </span>
        <ArrowRight size={16} aria-hidden />
      </button>
    );

  if (!path)
    return (
      <button type="button" onClick={() => setDrawer(true)} className={styles.sideCard} data-kind="cta">
        <Route size={18} aria-hidden />
        <span>
          <strong>Your path uses another version</strong>
          <small>Open it to work through the modules it was planned for.</small>
        </span>
        <ArrowRight size={16} aria-hidden />
      </button>
    );

  const { finished, total } = completion(path);
  const next = nextUp(path);
  const href = next && openHref(next, pageOf(next.module.id));
  return (
    <div className={styles.sideCard}>
      <div className={styles.sideHead}>
        <button type="button" className={styles.link} onClick={() => setDrawer(true)}>
          My path
        </button>
        <span className={styles.muted}>
          {`${finished} of ${total} done`}
        </span>
      </div>
      <ProgressBar finished={finished} total={total} />
      {next && href ? (
        <Link to={href} className={styles.sideNext}>
          <span className={styles.muted}>Next</span> {next.module.title} <ArrowRight size={14} aria-hidden />
        </Link>
      ) : (
        finished === total && <span className={styles.sideNext}>🎉 Path complete</span>
      )}
    </div>
  );
}

// The status of the module a sidebar link opens, if it is a module of the learner's path.
export function useSidebarStatus(docId: string | undefined): Status | null {
  const { path } = usePathOfThisVersion();
  const item = docId ? path?.items.find((candidate) => candidate.module.id === docId) : undefined;
  if (!path || !item) return null;
  return statusOf(path, item);
}

// Whether the path leaves out every one of its modules among these docs; false when none of them is a module.
export function useCategorySkipped(docIds: string[]): boolean {
  const { path } = usePathOfThisVersion();
  if (!path) return false;
  const items = path.items.filter((item) => docIds.includes(item.module.id));
  return items.length > 0 && items.every((item) => statusOf(path, item) === "skipped");
}
