// DotPath on any school's site, from one script tag. The same components as on the course site: the path
// panel at the right of every page, the assistant's button, sign-in; and on a lesson page, the module's
// status above the lesson and its checkpoint below it. Each sits in a shadow root, so the school's styles
// and ours stay apart.
import React, { useEffect, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import AskButton from "@pp/AskButton";
import AuthDialog from "@pp/AuthDialog";
import PathDrawer from "@pp/PathDrawer";
import { ModuleFinish, ModulePanel } from "@pp/ModulePage";
import { embedding } from "@pp/api";
import { usePathState } from "@pp/store";
import Designer, { DESIGNER_CSS } from "./Designer";
import { setTheme, themeSheet, themeStyle, type Theme } from "./theme";
import { config } from "./config";
import { LessonContext } from "./shims/docusaurus";
import { getSite, lessonAt, setSite, type EmbedSite } from "./site";

// The components' styles and base.css, put in by build.mjs.
const CSS = "__DOTPATH_CSS__";
const FONTS = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap";

// The session the API hands the panel, kept in this site's storage (only this site can read it).
const TOKEN_KEY = "dotpath.session";
let memoryToken: string | null = null;

function storedToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return memoryToken;
  }
}

function keepToken(token: string | null): void {
  memoryToken = token;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage blocked: the session lasts until the page reloads.
  }
}

let sheet: CSSStyleSheet | null = null;

// A shadow root with our styles: one stylesheet shared by every root where the browser allows it.
function shadowFor(host: HTMLElement): HTMLElement {
  const shadow = host.attachShadow({ mode: "open" });
  try {
    sheet ??= new CSSStyleSheet();
    if (!sheet.cssRules.length) sheet.replaceSync(CSS);
    // The school's theme after the components' styles, so its values win.
    shadow.adoptedStyleSheets = [sheet, themeSheet()];
  } catch {
    const style = document.createElement("style");
    style.textContent = CSS;
    shadow.append(style, themeStyle());
  }
  const root = document.createElement("div");
  root.className = "dp-root";
  shadow.append(root);
  return root;
}

const roots: ShadowRoot[] = [];

function mount(host: HTMLElement, content: ReactNode): () => void {
  const root = createRoot(shadowFor(host));
  roots.push(host.shadowRoot!);
  root.render(content);
  return () => {
    root.unmount();
    roots.splice(roots.indexOf(host.shadowRoot!), 1);
    host.remove();
  };
}

// The lesson blocks, again after the site changes pages without reloading.
let unmountLesson: (() => void) | null = null;

function mountLesson(attempt = 0): void {
  unmountLesson?.();
  unmountLesson = null;
  const lesson = lessonAt(window.location.pathname);
  if (!lesson) return;
  const content = document.querySelector<HTMLElement>(config.content ?? getSite().content);
  if (!content) {
    // A site that renders its pages in the browser may not have drawn the lesson yet.
    if (attempt < 20) window.setTimeout(() => mountLesson(attempt + 1), 150);
    return;
  }
  const above = document.createElement("div");
  const below = document.createElement("div");
  for (const [host, name] of [
    [above, "status"],
    [below, "checkpoint"],
  ] as const) {
    host.className = "dotpath-lesson";
    host.dataset.dotpath = name;
  }
  content.before(above);
  content.after(below);
  const undoAbove = mount(
    above,
    <LessonContext.Provider value={lesson}>
      <ModulePanel />
    </LessonContext.Provider>,
  );
  const undoBelow = mount(
    below,
    <LessonContext.Provider value={lesson}>
      <ModuleFinish />
    </LessonContext.Provider>,
  );
  unmountLesson = () => {
    undoAbove();
    undoBelow();
  };
  window.setTimeout(scrollToHash, 400);
}

// Links such as "#checkpoint" point into our shadow roots, where the browser does not look.
function scrollToHash(): void {
  const id = decodeURIComponent(window.location.hash.slice(1));
  if (!id || document.getElementById(id)) return;
  for (const root of roots) {
    const target = root.getElementById(id);
    if (target) {
      const top = target.getBoundingClientRect().top + window.scrollY - headerHeight() - 16;
      window.scrollTo({ top, behavior: "smooth" });
      return;
    }
  }
}

// The school's header, if it stays at the top while the page scrolls: a target goes below it, not under it.
function headerHeight(): number {
  for (const element of document.elementsFromPoint(8, 4)) {
    for (let node: Element | null = element; node && node !== document.body; node = node.parentElement) {
      const { position } = getComputedStyle(node);
      if (position === "fixed" || position === "sticky") return node.getBoundingClientRect().bottom;
    }
  }
  return 0;
}

// A site that changes pages with history.pushState: tell the components, and put the lesson blocks again.
function followNavigation(): void {
  const changed = () => {
    window.dispatchEvent(new Event("dotpath:navigate"));
    window.setTimeout(() => mountLesson(), 50);
  };
  for (const name of ["pushState", "replaceState"] as const) {
    const original = window.history[name];
    window.history[name] = function (this: History, ...args: Parameters<History["pushState"]>) {
      const before = window.location.pathname;
      const result = original.apply(this, args);
      if (window.location.pathname !== before) changed();
      else window.dispatchEvent(new Event("dotpath:navigate"));
      return result;
    } as History["pushState"];
  }
  window.addEventListener("popstate", () => window.setTimeout(() => mountLesson(), 50));
  window.addEventListener("hashchange", scrollToHash);
}

// While the panel is open on a wide screen, the school's page moves aside so the lesson stays readable.
function makeRoom(panel: ShadowRoot): void {
  const style = document.createElement("style");
  style.id = "dotpath-room";
  document.head.append(style);
  // The page moves at the panel's pace when the learner opens or closes it; on arrival it is already in place.
  let animate = false;
  window.setTimeout(() => (animate = true), 1000);
  const update = () => {
    const dock = panel.querySelector<HTMLElement>("[data-open]");
    const open = dock?.dataset.open === "true";
    const width = open ? Math.round(dock!.getBoundingClientRect().width) : 0;
    const pace = animate && dock?.dataset.dragging !== "true" ? "transition: margin-right 0.3s cubic-bezier(0.32, 0.72, 0, 1);" : "";
    style.textContent = `@media (min-width: 1200px) {
  body { margin-right: ${width}px !important; ${pace} }
}`;
  };
  const watch = new MutationObserver(update);
  const sizes = new ResizeObserver(update);
  const attach = () => {
    const dock = panel.querySelector<HTMLElement>("[data-open]");
    if (!dock) return false;
    watch.observe(dock, { attributes: true, attributeFilter: ["data-open", "data-dragging", "style"] });
    sizes.observe(dock);
    update();
    return true;
  };
  if (!attach()) {
    const wait = new MutationObserver(() => attach() && wait.disconnect());
    wait.observe(panel, { childList: true, subtree: true });
  }
}

// The window where the school's designers change the panel's look; one at a time.
let closeDesigner: (() => void) | null = null;

function openDesigner(): void {
  if (closeDesigner) return;
  const host = document.createElement("div");
  host.id = "dotpath-designer";
  document.body.append(host);
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = DESIGNER_CSS;
  const holder = document.createElement("div");
  shadow.append(style, holder);
  const root = createRoot(holder);
  closeDesigner = () => {
    root.unmount();
    host.remove();
    closeDesigner = null;
  };
  root.render(<Designer onClose={() => closeDesigner?.()} />);
}

// Whether the signed-in account may change the look here: the account menu then offers the design window.
// A link to the page with #dotpath-design opens it straight away.
function DesignerAccess(): null {
  const { account } = usePathState();
  const email = account?.email ?? null;
  useEffect(() => {
    embedding.design = null;
    closeDesigner?.();
    if (!email) return;
    let current = true;
    const headers: Record<string, string> = { "X-DotPath-Embed": "1" };
    const token = embedding.token();
    if (token) headers.Authorization = `Bearer ${token}`;
    fetch(`${config.api}/embed/designer`, { credentials: "include", headers })
      .then((response) => (response.ok ? response.json() : { designer: false }))
      .then((found: { designer?: boolean }) => {
        if (!current || !found.designer) return;
        embedding.design = openDesigner;
        if (window.location.hash === "#dotpath-design") openDesigner();
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [email]);
  return null;
}

async function start(): Promise<void> {
  const flag = window as unknown as { __dotpath?: boolean };
  if (flag.__dotpath) return; // the tag twice on one page
  flag.__dotpath = true;

  embedding.on = true;
  embedding.token = storedToken;
  embedding.keep = keepToken;

  try {
    const found = await fetch(`${config.api}/embed/site`);
    if (found.ok) {
      const site = (await found.json()) as EmbedSite & { theme?: Theme };
      setSite(site);
      if (site.theme) setTheme(site.theme);
    }
  } catch {
    // The service is down: the panel says so when the learner opens it.
  }

  if (!document.querySelector(`link[href="${FONTS}"]`)) {
    const fonts = document.createElement("link");
    fonts.rel = "stylesheet";
    fonts.href = FONTS;
    document.head.append(fonts);
  }

  const host = document.createElement("div");
  host.id = "dotpath";
  // Above the school's own page, its headers and chat buttons included.
  host.style.cssText = "position: relative; z-index: 2147483000;";
  document.body.append(host);
  mount(
    host,
    <>
      <PathDrawer />
      <AskButton />
      <AuthDialog />
      <DesignerAccess />
    </>,
  );
  makeRoom(host.shadowRoot!);
  mountLesson();
  followNavigation();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => void start());
else void start();
