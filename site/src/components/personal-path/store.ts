// The learner's session and path, shared by every part of the site that shows them: the navbar, the
// sidebar, module pages and the path page. The API keeps the path of a signed-in learner; this store only
// holds the latest copy it returned. A path planned before signing in is a draft the API keeps for a day;
// this browser remembers its id so the learner can sign up and keep it.
import { useEffect, useState, useSyncExternalStore } from "react";
import { ApiError, type Account, type PathApi, type Session } from "./api";
import type { CheckpointSummary, LearningPath } from "./model";

export type AuthMode = "sign-in" | "sign-up";

export interface PathState {
  ready: boolean; // the session has been asked for
  account: Account | null;
  path: LearningPath | null;
  // Set while the path is a draft: the learner has not signed in.
  draftId: string | null;
  auth: { mode: AuthMode; reason: string | null } | null; // the sign-in dialog, when open
  drawer: boolean; // the path panel at the right of every page
  panelTab: PanelTab; // what the panel shows: the path, or the assistant
  // A question another part of the page puts in the assistant's box, such as "why does my code fail".
  pendingQuestion: PendingQuestion | null;
}

export interface PendingQuestion {
  text: string;
  moduleId: string;
}

export type PanelTab = "path" | "ask";

const INITIAL: PathState = {
  ready: false,
  account: null,
  path: null,
  draftId: null,
  auth: null,
  drawer: false,
  panelTab: "path",
  pendingQuestion: null,
};
let state: PathState = INITIAL;
const listeners = new Set<() => void>();

function set(update: Partial<PathState>): void {
  state = { ...state, ...update };
  listeners.forEach((listener) => listener());
}

export function usePathState(): PathState {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
    () => INITIAL,
  );
}

export const getPathState = (): PathState => state;

// Remembered in this browser: only the id of a draft, never the path or the session.
const DRAFT_KEY = "humblebeeai.personal-path.draft";

function rememberDraft(draftId: string | null): void {
  try {
    if (draftId) window.localStorage.setItem(DRAFT_KEY, draftId);
    else window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Storage blocked: the draft lasts for this visit.
  }
}

function rememberedDraft(): string | null {
  try {
    return window.localStorage.getItem(DRAFT_KEY);
  } catch {
    return null;
  }
}

let started: Promise<void> | null = null;

const SIGN_IN_ERRORS: Record<string, string> = {
  cancelled: "Signing in with Google was cancelled.",
  google: "Google could not confirm your account. Try again, or use your email and a password.",
};

// Coming back from Google without signing in, the page's address ends in #sign-in-error=<reason>.
function signInError(): string | null {
  const match = /^#sign-in-error=(\w+)$/.exec(window.location.hash);
  if (!match) return null;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return SIGN_IN_ERRORS[match[1]] ?? SIGN_IN_ERRORS.google;
}

// Asks the API who is signed in, once per page load.
export function startSession(api: PathApi): Promise<void> {
  started ??= (async () => {
    try {
      const session = await api.session();
      if (session.account) return applySession(session);
      const error = signInError();
      if (error) openAuth("sign-in", error);
      const draftId = rememberedDraft();
      const draft = draftId ? await api.draft(draftId).catch(() => null) : null;
      if (!draft) rememberDraft(null);
      set({
        ready: true,
        account: null,
        path: draft,
        draftId: draft ? draftId : null,
      });
    } catch {
      set({ ready: true }); // the service is down; pages show what they can without it
    }
  })();
  return started;
}

export function applySession(session: Session): void {
  rememberDraft(null);
  set({
    ready: true,
    account: session.account,
    path: session.path,
    draftId: null,
    auth: null,
  });
}

export function setPath(path: LearningPath | null): void {
  set({ path });
}

export function setDraft(path: LearningPath, draftId: string): void {
  rememberDraft(draftId);
  set({ path, draftId });
}

// Whether the path panel is open, remembered in this browser across pages and visits.
const DRAWER_KEY = "humblebeeai.personal-path.drawer";

export function setDrawer(open: boolean): void {
  try {
    window.localStorage.setItem(DRAWER_KEY, open ? "open" : "closed");
  } catch {
    // Not remembered; the panel still opens and closes.
  }
  set({ drawer: open });
}

export function setPanelTab(tab: PanelTab): void {
  set({ panelTab: tab });
}

// The assistant's button: opens the panel at its Ask tab.
export function openAssistant(): void {
  setDrawer(true);
  setPanelTab("ask");
}

export function rememberedDrawer(): boolean {
  try {
    return window.localStorage.getItem(DRAWER_KEY) === "open";
  } catch {
    return false;
  }
}

export function openAuth(mode: AuthMode, reason: string | null = null): void {
  set({ auth: { mode, reason } });
}

export function closeAuth(): void {
  set({ auth: null });
}

// A request for the signed-in path that finds the session over (expired, signed out in another tab).
export function handleSignedOut(reason: unknown): boolean {
  if (reason instanceof ApiError && reason.status === 401 && state.account) {
    set({ account: null, path: null });
    openAuth("sign-in", "Your session has ended. Sign in again to continue.");
    return true;
  }
  return false;
}

// Which modules of a curriculum version have a checkpoint; asked once per version.
const checkpointLists = new Map<string, Promise<Record<string, CheckpointSummary>>>();

export function useCheckpoints(
  api: PathApi | null,
  version: string | undefined,
): Record<string, CheckpointSummary> {
  const [found, setFound] = useState<Record<string, CheckpointSummary>>({});
  useEffect(() => {
    if (!api || !version) return;
    if (!checkpointLists.has(version))
      checkpointLists.set(
        version,
        api.checkpoints(version).catch(() => {
          checkpointLists.delete(version);
          return {};
        }),
      );
    let current = true;
    void checkpointLists.get(version)!.then((list) => current && setFound(list));
    return () => {
      current = false;
    };
  }, [api, version]);
  return found;
}

// Opens the assistant with a question in its box, such as one about failing code; the learner sends it.
export function askAssistant(question: PendingQuestion): void {
  set({ pendingQuestion: question });
  openAssistant();
}

export function takePendingQuestion(): PendingQuestion | null {
  const question = state.pendingQuestion;
  if (question) set({ pendingQuestion: null });
  return question;
}

// The coding problem open on the page: the learner's code as it is now, and what the last run of the tests
// said. Kept outside the shared state, since it changes with every key; the assistant reads it when asked.
export interface OpenProblem {
  moduleId: string;
  code: string;
  lastRun: string | null; // a summary of the last run, or null before the tests ran
}

let openProblem: OpenProblem | null = null;

export function setOpenProblem(problem: OpenProblem | null): void {
  openProblem = problem;
}

export function currentOpenProblem(): OpenProblem | null {
  return openProblem;
}
