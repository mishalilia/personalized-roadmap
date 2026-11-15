// The learner's path in this browser, kept in step across the page and every component that shows it.
import { useEffect, useState } from "react";
import type { LearningPath, SavedPath } from "./model";
import { CHANGED_EVENT, loadSavedPath, savePath } from "./storage";

export function useSavedPath(): [SavedPath | null, (path: LearningPath) => void] {
  const [saved, setSaved] = useState<SavedPath | null>(null);

  useEffect(() => {
    const refresh = () => setSaved(loadSavedPath());
    refresh();
    window.addEventListener(CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  // A changed path keeps the site version it was planned for.
  const update = (path: LearningPath) => {
    const current = loadSavedPath();
    savePath({ path, siteVersion: path.curriculum_site_version ?? current?.siteVersion ?? null });
  };
  return [saved, update];
}
