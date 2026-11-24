// The school's course as the API describes it for this site (GET /embed/site): where each module's lesson
// lives here, per curriculum version, and which element of a lesson page holds the lesson. An engineer writes
// it when the school's course is converted.

export interface SiteDoc {
  id: string; // the module's id in the curriculum
  path: string; // its lesson page on this site
}

export interface SiteVersion {
  name: string; // the curriculum's site version, as a path names it
  label: string;
  docs: SiteDoc[];
}

export interface EmbedSite {
  versions: SiteVersion[];
  content: string;
}

let site: EmbedSite = { versions: [], content: "main article" };

export function setSite(found: EmbedSite): void {
  site = found;
}

export function getSite(): EmbedSite {
  return site;
}

const bare = (path: string) => path.replace(/\/(index\.html?)?$/, "") || "/";

// The module whose lesson is the page at `pathname`, and the version of the course it belongs to.
export function lessonAt(pathname: string): { id: string; version: string } | null {
  const here = bare(pathname);
  for (const version of site.versions) {
    const doc = version.docs.find((candidate) => bare(candidate.path) === here);
    if (doc) return { id: doc.id, version: version.name };
  }
  return null;
}
