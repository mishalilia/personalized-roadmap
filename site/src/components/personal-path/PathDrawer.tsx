// The personal path as a panel at the right of every page: the learner opens it while reading a module,
// answers the questions, reviews and changes their path, and follows it without leaving the course. On wide
// screens the page moves aside to make room, so the module stays readable next to the path.
import React, { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "@docusaurus/router";
import { MessageCircle, Route } from "lucide-react";
import AccountMenu from "./AccountMenu";
import { usePathApi } from "./api";
import { useModulePages } from "./useModulePages";
import { completion } from "./model";
import PathChat from "./PathChat";
import PathMap, { MapButton } from "./PathMap";
import PersonalPath from "./PersonalPath";
import { openAuth, rememberedDrawer, setDrawer, setPanelTab, setPath, usePathState } from "./store";
import { ProgressRing } from "./ui";
import styles from "./path.module.css";

// While the panel is open, the page moves aside on wide screens, at the panel's pace. A rule of its own, since
// Docusaurus resets the classes of <html> and <body> on every page change.
// The site's own "back to top" button sits at the bottom right, under the panel: it moves left of the panel
// where the page makes room, and goes away where the panel covers the page.
const makeRoom = (width: number) => `@media (min-width: 1200px) {
  .main-wrapper, .footer { margin-right: ${width}px; }
  .theme-back-to-top-button { right: calc(${width}px + 1.3rem); }
}
@media (max-width: 1199.98px) {
  .theme-back-to-top-button { display: none; }
}`;

// The panel's width, which the learner can drag; remembered in this browser.
const WIDTH_KEY = "personal-path-panel-width";
const DEFAULT_WIDTH = 460;
const MIN_WIDTH = 360;
// The page keeps at least this much room beside the panel.
const PAGE_ROOM = 480;

function clampWidth(width: number): number {
  const max = Math.max(MIN_WIDTH, window.innerWidth - PAGE_ROOM);
  return Math.round(Math.min(Math.max(width, MIN_WIDTH), max));
}

function rememberedWidth(): number {
  try {
    const saved = Number(window.localStorage.getItem(WIDTH_KEY));
    return saved ? clampWidth(saved) : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

function rememberWidth(width: number): void {
  try {
    window.localStorage.setItem(WIDTH_KEY, String(width));
  } catch {
    // Without storage the width lasts until the page reloads.
  }
}
const MOVE_PAGE = `@media (min-width: 1200px) and (prefers-reduced-motion: no-preference) {
  .main-wrapper, .footer { transition: margin-right 0.3s cubic-bezier(0.32, 0.72, 0, 1); }
}`;

export default function PathDrawer(): ReactNode {
  const api = usePathApi();
  const { drawer, ready, account, path, auth, panelTab: tab } = usePathState();
  const { pathname } = useLocation();
  // The path page shows the path itself; a panel beside it would show it twice.
  const onPathPage = pathname.startsWith("/personal-path");
  const open = drawer && !onPathPage;
  // The path mounts the first time the panel opens, then stays, so closing slides it out instead of emptying it.
  const [opened, setOpened] = useState(false);
  const [map, setMap] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);
  useEffect(() => setWidth(rememberedWidth()), []);
  // After a checkpoint the server may still be working out suggestions for the rest of the path: ask for the
  // path again every few seconds until they arrive, on whatever page the learner is.
  const pending = account ? path?.suggestions_pending : null;
  useEffect(() => {
    if (!api || !pending) return;
    const timer = window.setInterval(() => {
      api.session().then(
        (session) => {
          if (session.path && session.path.suggestions_pending !== pending) setPath(session.path);
        },
        () => undefined,
      );
    }, 5000);
    return () => window.clearInterval(timer);
  }, [api, pending]);
  // The module whose page is open, so that a question can be about it.
  const pageOf = useModulePages(path?.curriculum_site_version ?? null);
  const here = pathname.replace(/\/$/, "");
  const pageModuleId = path?.items.find((item) => pageOf(item.module.id)?.replace(/\/$/, "") === here)?.module
    .id;
  useEffect(() => {
    if (open) setOpened(true);
  }, [open]);

  // A closed panel stays in the page for its slide, but out of reach of the keyboard and screen readers.
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.toggleAttribute("inert", !open);
  }, [open, api, onPathPage]);

  useEffect(() => {
    if (rememberedDrawer()) setDrawer(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    // Escape closes the map or a dialog first; the panel only when nothing is open over it. The panel's own
    // root is the page, or the shadow root it sits in when embedded in another site.
    const root = (panel.current?.getRootNode() ?? document) as Document | ShadowRoot;
    const onKey = (event: KeyboardEvent) =>
      event.key === "Escape" && !auth && !root.querySelector("[aria-modal=true]") && setDrawer(false);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [open, auth]);

  // On a phone the panel covers the page, so following a link in it closes it; arriving from the old path
  // page, which opens the panel, does not.
  const previous = useRef(pathname);
  useEffect(() => {
    const from = previous.current;
    previous.current = pathname;
    if (from === pathname || from.startsWith("/personal-path")) return;
    if (window.matchMedia("(max-width: 996px)").matches) setDrawer(false);
  }, [pathname]);

  if (!api || onPathPage) return null;
  const progress = path?.confirmed_at ? completion(path) : null;

  return (
    <>
      {map && path && <PathMap path={path} onClose={() => setMap(false)} />}
      <div
        className={styles.dock}
        data-open={open}
        data-dragging={dragging}
        style={{ "--dock-width": `min(${width}px, calc(100vw - 44px))` } as React.CSSProperties}
      >
        <style>{(dragging ? "" : MOVE_PAGE) + (open ? makeRoom(width) : "")}</style>
        {open && (
          <div
            className={styles.resizeHandle}
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize the panel"
            aria-valuenow={width}
            aria-valuemin={MIN_WIDTH}
            tabIndex={0}
            title="Drag to resize"
            onPointerDown={(event) => {
              event.preventDefault();
              event.currentTarget.setPointerCapture(event.pointerId);
              setDragging(true);
            }}
            onPointerMove={(event) => {
              if (dragging) setWidth(clampWidth(window.innerWidth - event.clientX));
            }}
            onPointerUp={(event) => {
              event.currentTarget.releasePointerCapture(event.pointerId);
              setDragging(false);
              rememberWidth(width);
            }}
            onDoubleClick={() => {
              setWidth(DEFAULT_WIDTH);
              rememberWidth(DEFAULT_WIDTH);
            }}
            onKeyDown={(event) => {
              const step = event.key === "ArrowLeft" ? 24 : event.key === "ArrowRight" ? -24 : 0;
              if (!step) return;
              event.preventDefault();
              const next = clampWidth(width + step);
              setWidth(next);
              rememberWidth(next);
            }}
          />
        )}
        <button
          type="button"
          className={styles.drawerTab}
          onClick={() => setDrawer(!open)}
          aria-expanded={open}
          aria-label={
            open
              ? "Close my path"
              : progress
                ? `My path: ${progress.finished} of ${progress.total} modules`
                : "Open my path"
          }
          title={open ? "Close my path" : undefined}
        >
          {progress ? (
            <ProgressRing finished={progress.finished} total={progress.total} size={26} label={false} />
          ) : (
            <Route size={18} aria-hidden />
          )}
          <span>{path ? "My path" : "Get your path"}</span>
        </button>
        <aside ref={panel} className={styles.drawer} aria-label="My path">
          <header className={styles.drawerHead}>
            <strong>My path</strong>
            {progress && (
              <span className={styles.muted}>
                {progress.finished} of {progress.total} done
              </span>
            )}
            <span className={styles.drawerTools}>
              {path && <MapButton onOpen={() => setMap(true)} />}
              {ready &&
                (account ? (
                  <AccountMenu
                    email={account.email}
                    hasPassword={account.has_password}
                    reviewer={account.reviewer}
                  />
                ) : (
                  <button type="button" className={styles.ghostSm} onClick={() => openAuth("sign-in")}>
                    Sign in
                  </button>
                ))}
            </span>
          </header>
          <div className={styles.panelTabs} role="tablist" aria-label="My path">
            <button
              type="button"
              role="tab"
              id="panel-tab-path"
              aria-selected={tab === "path"}
              aria-controls="panel-path"
              onClick={() => setPanelTab("path")}
            >
              <Route size={15} aria-hidden /> Path
            </button>
            <button
              type="button"
              role="tab"
              id="panel-tab-ask"
              aria-selected={tab === "ask"}
              aria-controls="panel-ask"
              onClick={() => setPanelTab("ask")}
            >
              <MessageCircle size={15} aria-hidden /> Ask
            </button>
          </div>
          {/* Both stay mounted, so the path keeps its place and the conversation its messages. */}
          <div
            className={styles.drawerBody}
            role="tabpanel"
            id="panel-path"
            aria-labelledby="panel-tab-path"
            hidden={tab !== "path"}
          >
            {(open || opened) && <PersonalPath />}
          </div>
          <div
            className={styles.drawerBody}
            role="tabpanel"
            id="panel-ask"
            aria-labelledby="panel-tab-ask"
            hidden={tab !== "ask"}
          >
            {(open || opened) && <PathChat api={api} path={path} pageModuleId={pageModuleId} />}
          </div>
        </aside>
      </div>
    </>
  );
}
