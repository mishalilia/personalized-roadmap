// Where each module of a path lives on this site. A path is planned for one curriculum version, so its
// modules link to that version's pages, which keep the content the planner saw.
import { useAllDocsData } from "@docusaurus/plugin-content-docs/client";

export function useModulePages(
  siteVersion: string | null,
): (moduleId: string) => string | undefined {
  const versions = useAllDocsData().default?.versions ?? [];
  const version = versions.find((candidate) => candidate.name === siteVersion);
  const pages = new Map(version?.docs.map((doc) => [doc.id, doc.path]) ?? []);
  return (moduleId) => pages.get(moduleId);
}

export function useVersionLabel(siteVersion: string | null): string | undefined {
  const versions = useAllDocsData().default?.versions ?? [];
  return versions.find((candidate) => candidate.name === siteVersion)?.label;
}
