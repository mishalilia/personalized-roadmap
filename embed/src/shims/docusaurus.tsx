// What the personal-path components take from Docusaurus, for a site that is not one. The build (build.mjs)
// points each @docusaurus/... import at the export of the same name here.
import React, { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import { config } from "../config";
import { getSite, lessonAt } from "../site";
import { useTheme } from "../theme";

// Pages that stay on the course site: the path page, public progress and the course team's pages.
const COURSE_SITE_PAGES = ["/personal-path", "/progress", "/review", "/report", "/img/"];

function onCourseSite(path: string): boolean {
  return COURSE_SITE_PAGES.some((page) => path === page.replace(/\/$/, "") || path.startsWith(page));
}

function resolve(to: string | undefined): string | undefined {
  if (!to || !to.startsWith("/") || to.startsWith("//")) return to;
  return onCourseSite(to) ? `${config.site}${to}` : to;
}

// @docusaurus/Link: a plain link. Lesson pages are this site's own; the course site's pages get its address.
export function Link({
  to,
  href,
  children,
  ...rest
}: { to?: string; href?: string; children?: ReactNode } & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a href={resolve(to ?? href)} {...rest}>
      {children}
    </a>
  );
}

// @docusaurus/useBaseUrl: an address on the course site, or the school's own picture for the assistant.
export function useBaseUrl(path: string): string {
  // A hook like Docusaurus's, so it may follow the theme: the designer's logo, the tag's, or the star.
  const theme = useTheme();
  if (path === "/img/hbai-logo.png") return theme.logo ?? config.logo ?? STAR;
  return resolve(path) ?? path;
}

// @docusaurus/BrowserOnly: the embed only ever runs in a browser.
export function BrowserOnly({ children }: { children?: () => ReactNode; fallback?: ReactNode }) {
  return <>{children ? children() : null}</>;
}

// @docusaurus/useDocusaurusContext: the API's address and Python's, as docusaurus.config.ts gives them.
export function useDocusaurusContext() {
  return {
    siteConfig: {
      customFields: {
        personalPathApi: config.api,
        pyodideUrl: config.pyodide ?? "",
      },
    },
  };
}

// @docusaurus/router: where the learner is. A site that changes pages without reloading (history.pushState)
// tells us through the events the embed adds (main.tsx).
function subscribe(changed: () => void): () => void {
  window.addEventListener("popstate", changed);
  window.addEventListener("dotpath:navigate", changed);
  return () => {
    window.removeEventListener("popstate", changed);
    window.removeEventListener("dotpath:navigate", changed);
  };
}

export function useLocation() {
  const href = useSyncExternalStore(subscribe, () => window.location.href);
  const url = new URL(href);
  return { pathname: url.pathname, search: url.search, hash: url.hash };
}

// @docusaurus/theme-common's Collapsible: shown or not; `lazy` content mounts only when shown.
export function Collapsible({
  collapsed,
  lazy,
  children,
}: {
  collapsed: boolean;
  lazy?: boolean;
  children?: ReactNode;
  [other: string]: unknown;
}) {
  if (collapsed && lazy) return null;
  return <div hidden={collapsed}>{children}</div>;
}

// @docusaurus/plugin-content-docs/client: the course's versions and pages as the API describes this site, and
// the lesson the panel stands beside (given by the element the embed mounts it in).
export function useAllDocsData() {
  return { default: { versions: getSite().versions } };
}

export const LessonContext = createContext<{ id: string; version: string } | null>(null);

export function useDoc() {
  const here = useContext(LessonContext) ?? lessonAt(window.location.pathname);
  return { metadata: { id: here?.id ?? "" } };
}

export function useDocsVersion() {
  const here = useContext(LessonContext) ?? lessonAt(window.location.pathname);
  return { version: here?.version ?? getSite().versions[0]?.name ?? "current" };
}

export function useActiveVersion() {
  return { name: useDocsVersion().version };
}

// DotPath's mark, for the assistant's button when the school gives no picture of its own.
const STAR =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="32" fill="#141414"/>' +
      '<path d="M32 9l5.6 17.4L55 32l-17.4 5.6L32 55l-5.6-17.4L9 32l17.4-5.6z" fill="#fff500"/></svg>',
  );
