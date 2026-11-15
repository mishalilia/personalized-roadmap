// The personal path as the Personalized Roadmap API returns it. The same JSON is what learners download,
// and what the project's own app opens, so this file only adds what a browser needs on top of it.

export type Level = "beginner" | "intermediate" | "advanced";
export type Choice = "study" | "prove" | "skip";

export const LEVELS: Level[] = ["beginner", "intermediate", "advanced"];

export interface Question {
  id: string;
  text: string;
  placeholder: string;
}

export interface CurriculumInfo {
  version: string;
  site_version: string | null;
  title: string;
  licence: string;
}

export interface QuestionsResponse {
  questions: Question[];
  curriculum: CurriculumInfo; // the version new paths are planned for
  versions: CurriculumInfo[]; // every version whose paths still work
  personalization_available: boolean;
}

export interface LevelAssessment {
  level: Level;
  evidence: string[];
  confidence: "low" | "medium" | "high";
}

export interface Module {
  id: string;
  title: string;
  description: string;
  section: string[];
  url: string;
  checklist: string[];
  hours?: { low: number; high: number } | null;
}

// "practice": the questions are passed and the module's coding problem is next.
export type Progress = "not_started" | "done" | "practice" | "passed" | "failed";

export interface PathItem {
  module: Module;
  suggested: Choice;
  reason: string;
  choice: Choice;
  // Absent in paths saved before checkpoints existed.
  progress?: Progress;
  attempts?: number;
  last_score?: string | null;
  adjustment?: string | null;
}

export interface Proposal {
  module_id: string;
  choice: Choice;
  reason: string;
}

export interface Attribution {
  title: string;
  author: string;
  url: string;
  licence: string;
  licence_url: string;
}

export interface TimeEstimate {
  path_low: number;
  path_high: number;
  course_low: number;
  course_high: number;
  modules_without_estimate: number;
}

export interface LearningPath {
  id?: string | null;
  curriculum_site_version?: string | null;
  level: Level | null;
  assessment: LevelAssessment | null;
  items: PathItem[];
  personalization_unavailable: boolean;
  curriculum_version: string;
  attribution: Attribution;
  changes: string;
  generated_at: string;
  confirmed_at: string | null;
  answers?: Record<string, string>;
  proposals?: Proposal[];
  // Worked out by the API from the progress; read-only here.
  locked_module_ids?: string[];
  blocking_module_id?: string | null;
  time_estimate?: TimeEstimate;
  // The learner chose to share anonymous progress events with the course's platform.
  share_progress?: boolean;
}

export interface CheckpointSummary {
  status: "draft" | "reviewed";
  questions_per_attempt: number;
  pass_mark: number;
  has_problem: boolean;
}

export interface CodingProblem {
  module_id: string;
  title: string;
  prompt: string;
  starter_code: string;
  tests: string;
  packages: string[];
}

export interface AskedQuestion {
  id: string;
  topic: string;
  text: string;
  options: string[];
}

export interface CheckpointQuestions {
  module_id: string;
  status: "draft" | "reviewed";
  attempt: number;
  pass_mark: number;
  questions: AskedQuestion[];
}

export interface Grade {
  attempt: number;
  score: number;
  total: number;
  passed: boolean;
  effortless: boolean;
  // The right answer and its explanation come only after a pass.
  feedback: {
    id: string;
    topic: string;
    correct: boolean;
    answer: number | null;
    explanation: string | null;
  }[];
  review_topics: string[];
  problem_pending: boolean;
}

// A path kept in this browser, with the site version it was planned for.
export interface SavedPath {
  path: LearningPath;
  siteVersion: string | null;
}

export const canBeProved = (item: PathItem): boolean =>
  item.module.checklist.length > 0;

// The learner's own choice replaces the planner's; any change asks for a new confirmation.
export function withChoice(
  path: LearningPath,
  moduleId: string,
  choice: Choice,
): LearningPath {
  return {
    ...path,
    items: path.items.map((item) =>
      item.module.id === moduleId ? { ...item, choice } : item,
    ),
    proposals: (path.proposals ?? []).filter((p) => p.module_id !== moduleId),
    confirmed_at: null,
  };
}

export function confirm(path: LearningPath): LearningPath {
  return { ...path, confirmed_at: new Date().toISOString() };
}

export const progressOf = (item: PathItem): Progress => item.progress ?? "not_started";

export const isLocked = (path: LearningPath, moduleId: string): boolean =>
  (path.locked_module_ids ?? []).includes(moduleId);

// The first module the learner has yet to finish, unless it is locked: what to do next.
export function nextUp(path: LearningPath): PathItem | undefined {
  return path.items.find(
    (item) => item.choice !== "skip" && !isFinished(item) && !isLocked(path, item.module.id),
  );
}

export const isFinished = (item: PathItem): boolean =>
  ["done", "passed"].includes(progressOf(item));

// Included modules finished, out of all included modules.
export function completion(path: LearningPath): { finished: number; total: number } {
  const included = path.items.filter((item) => item.choice !== "skip");
  return { finished: included.filter(isFinished).length, total: included.length };
}

export function count(path: LearningPath, choice: Choice): number {
  return path.items.filter((item) => item.choice === choice).length;
}

// Consecutive items of the same section, in course order.
export function bySection(
  items: PathItem[],
): { section: string; items: PathItem[] }[] {
  const groups: { section: string; items: PathItem[] }[] = [];
  for (const item of items) {
    const section = item.module.section.join(" › ");
    const last = groups[groups.length - 1];
    if (last && last.section === section) last.items.push(item);
    else groups.push({ section, items: [item] });
  }
  return groups;
}

// Enough of a check to refuse a file that is not a path; the API validated the path when it made it.
export function isLearningPath(value: unknown): value is LearningPath {
  const path = value as LearningPath;
  return (
    typeof path === "object" &&
    path !== null &&
    Array.isArray(path.items) &&
    typeof path.curriculum_version === "string" &&
    path.items.every(
      (item) =>
        typeof item?.module?.id === "string" &&
        ["study", "prove", "skip"].includes(item.choice),
    )
  );
}
