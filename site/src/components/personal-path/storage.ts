// The learner's path lives in this browser only: there are no accounts. Storage can be unavailable
// (private windows, blocked site data), so every access is guarded and the page works without it.
import { isLearningPath, type SavedPath } from "./model";

const KEY = "humblebeeai.personal-path";
export const CHANGED_EVENT = "personal-path-changed";

export function loadSavedPath(): SavedPath | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as SavedPath;
    return isLearningPath(saved?.path) ? saved : null;
  } catch {
    return null;
  }
}

export function savePath(saved: SavedPath | null): void {
  try {
    if (saved) window.localStorage.setItem(KEY, JSON.stringify(saved));
    else window.localStorage.removeItem(KEY);
  } catch {
    // The path still works for this visit; it is just not remembered.
  }
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

// The onboarding answers typed so far, so a reload does not lose them.
const DRAFT_KEY = "humblebeeai.personal-path.answers";

export function loadDraft(): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

export function saveDraft(answers: Record<string, string> | null): void {
  try {
    if (answers) window.localStorage.setItem(DRAFT_KEY, JSON.stringify(answers));
    else window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Not remembered; the form still works.
  }
}
