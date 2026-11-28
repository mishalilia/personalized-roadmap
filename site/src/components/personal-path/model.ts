// The personal path as the Personalized Roadmap API returns it. The same JSON is what learners download,
// and what the project's own app opens, so this file only adds what a browser needs on top of it.

export type Level = "beginner" | "intermediate" | "advanced";
export type Choice = "study" | "prove" | "skip";

export const LEVELS: Level[] = ["beginner", "intermediate", "advanced"];

export interface QuestionOption {
  id: string;
  label: string;
}

// single: one option; multiple: any number; check: a code question with one right option, which only the
// server knows; text: written freely. A choice question's placeholder hints at its optional details.
export interface Question {
  id: string;
  text: string;
  kind: "text" | "single" | "multiple" | "check";
  placeholder: string;
  options: QuestionOption[];
  code: string;
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
  // A capstone: the learner submits a project for review instead of taking a checkpoint.
  is_project?: boolean;
  // The module's parts: its page's second-level headings, with what each says the learner will be able to do.
  topics?: Topic[];
}

export interface Topic {
  title: string;
  outcomes: string[];
  anchor?: string | null; // the heading's id on the module page, as the course's authors set it
}

// "practice": the questions are passed and the module's coding problem is next.
// "submitted": a project waiting for a reviewer; "returned": sent back with a comment.
export type Progress = "not_started" | "done" | "practice" | "passed" | "failed" | "submitted" | "returned";

export interface PathItem {
  module: Module;
  suggested: Choice;
  reason: string;
  choice: Choice;
  // Absent in paths saved before checkpoints existed.
  progress?: Progress;
  attempts?: number;
  last_score?: string | null;
  missed_topics?: string[]; // the topics of the wrong answers in the last checkpoint attempt
  // For a module to study: topics the learner can skim, suggested by the planner or chosen by the learner.
  // A reason only on paths planned before 27 November.
  skim?: { topic: string; reason?: string | null; chosen?: boolean }[];
  // For a module to study: topics the learner leaves out; its checkpoint does not ask about them.
  skip_topics?: { topic: string; reason?: string | null; chosen?: boolean }[];
  finished_topics?: string[]; // topics the learner marked as finished: their own tally, not a pass
  adjustment?: string | null;
}

// A change to a module not started yet, suggested after a checkpoint: lighter after an easy pass, heavier
// after a failure. It changes either the module's choice or how the learner takes one of its topics.
export interface Proposal {
  module_id: string;
  choice?: Choice | null;
  reason: string;
  topic?: string | null;
  topic_choice?: TopicChoice | null;
  after_failure?: boolean;
}

// What a proposal would change, in words: "skim Readable Python" or "study this module".
export function proposalAction(proposal: Proposal): string {
  if (proposal.topic) {
    const how = { study: "study in full", skim: "skim", skip: "skip" }[proposal.topic_choice ?? "study"];
    return `${how}: ${proposal.topic}`;
  }
  return `${proposal.choice} the module`;
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
  title?: string | null; // a short name after the learner's goal, from the planner
  proposals?: Proposal[];
  // What the path changed by itself after the last failed checkpoint, until the learner has seen it.
  changed_after_checkpoint?: Proposal[];
  // Set while the model works out suggestions after a checkpoint; the page asks for the path again meanwhile.
  suggestions_pending?: string | null;
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
  topic?: string | null; // the module's topic it practises
  topic_anchor?: string | null; // that topic's heading id on the module page
}

export interface AskedQuestion {
  id: string;
  topic: string;
  text: string;
  options: string[]; // none for an open question
  kind?: "choice" | "open"; // open: answered in the learner's own words, marked against a rubric
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
    kind?: "choice" | "open";
    graded?: boolean; // false: an open answer no model could mark, left out of the score
    answer: number | null;
    explanation: string | null; // for an open question, a full answer
    comment?: string | null; // an open answer: what it gets right and what it leaves out
  }[];
  review_topics: string[];
  problem_pending: boolean;
}

export const canBeProved = (item: PathItem): boolean => item.module.checklist.length > 0;

export const progressOf = (item: PathItem): Progress => item.progress ?? "not_started";

export const isLocked = (path: LearningPath, moduleId: string): boolean =>
  (path.locked_module_ids ?? []).includes(moduleId);

// The first module the learner has yet to finish, unless it is locked: what to do next.
export function nextUp(path: LearningPath): PathItem | undefined {
  return path.items.find(
    (item) => item.choice !== "skip" && !isFinished(item) && !isLocked(path, item.module.id),
  );
}

export const isFinished = (item: PathItem): boolean => ["done", "passed"].includes(progressOf(item));

// Included modules finished, out of all included modules.
export function completion(path: LearningPath): { finished: number; total: number } {
  const included = path.items.filter((item) => item.choice !== "skip");
  return { finished: included.filter(isFinished).length, total: included.length };
}

export function count(path: LearningPath, choice: Choice): number {
  return path.items.filter((item) => item.choice === choice).length;
}

// Consecutive items of the same section, in course order.
export function bySection(items: PathItem[]): { section: string; items: PathItem[] }[] {
  const groups: { section: string; items: PathItem[] }[] = [];
  for (const item of items) {
    const section = item.module.section.join(" › ");
    const last = groups[groups.length - 1];
    if (last && last.section === section) last.items.push(item);
    else groups.push({ section, items: [item] });
  }
  return groups;
}

export const isIncluded = (item: PathItem): boolean => item.choice !== "skip";

// Where a module stands for the learner, in the words the interface uses.
export type Status =
  "skipped" | "locked" | "finished" | "practice" | "failed" | "submitted" | "returned" | "next" | "todo";

export function statusOf(path: LearningPath, item: PathItem): Status {
  if (!isIncluded(item)) return "skipped";
  if (isLocked(path, item.module.id)) return "locked";
  const progress = progressOf(item);
  if (isFinished(item)) return "finished";
  if (progress === "practice") return "practice";
  if (progress === "failed") return "failed";
  if (progress === "submitted") return "submitted";
  if (progress === "returned") return "returned";
  if (path.confirmed_at && nextUp(path)?.module.id === item.module.id) return "next";
  return "todo";
}

// The module's place among those the learner works through: "2 of 9".
export function stepOf(path: LearningPath, moduleId: string): { step: number; total: number } | null {
  const included = path.items.filter(isIncluded);
  const index = included.findIndex((item) => item.module.id === moduleId);
  return index < 0 ? null : { step: index + 1, total: included.length };
}

// The next module the path works through after this one, in course order.
export function nextAfter(path: LearningPath, moduleId: string): PathItem | undefined {
  const index = path.items.findIndex((item) => item.module.id === moduleId);
  return path.items.slice(index + 1).find(isIncluded);
}

export function hours(low: number, high: number): string {
  const round = (value: number) => (value < 10 ? Math.round(value * 2) / 2 : Math.round(value));
  return round(low) === round(high) ? `${round(low)} h` : `${round(low)}–${round(high)} h`;
}

export interface Submission {
  id: string;
  email: string;
  module_id: string;
  module_title: string;
  link: string | null;
  note: string;
  file_name: string | null;
  file_size: number | null;
  // "reviewing": the model is reading it; "submitted": waiting for a person (the API runs without a model);
  // "failed": not reviewed, as the project could not be read or no model answered: the comment says why.
  status: "reviewing" | "submitted" | "accepted" | "returned" | "failed";
  review_comment: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null; // "model", or a reviewer's email
  ai_review: ProjectReview | null;
}

export interface ReviewedCriterion {
  name: string;
  about: "behaviour" | "artefact";
  verdict: "met" | "not_met" | "unverified";
  evidence: { file: string; quote: string }[];
  comment: string;
  // The model said met, but its evidence is not in the project: it does not count.
  evidence_missing: boolean;
  // About behaviour, but shown only in what the learner wrote, not in what their code produced.
  output_missing: boolean;
}

export interface ProjectReview {
  passed: boolean;
  level: string | null;
  levels: { name: string; passing: boolean; criteria: ReviewedCriterion[] }[];
  feedback: string;
  files_read: number;
  files_listed: number;
  source: string;
  outputs: string[]; // the project's texts its code produced
}

export const MAX_ARCHIVE_MB = 20;

// The anchor Docusaurus gives a heading without an id of its own: lower case, punctuation dropped, spaces as
// hyphens. The course's headings mostly set their own id, which wins.
export function headingAnchor(title: string): string {
  return title
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}\p{Pc}\- ]/gu, "")
    .replace(/ /g, "-");
}

const withoutNumber = (title: string) => title.replace(/^\d+\.\s*/, "").trim().toLowerCase();

// The topics to review after a failed checkpoint, each with the anchor of its section on the module page.
// A question's topic is one of the module's own topics, named with or without its heading number.
export function topicsToReview(item: PathItem): { title: string; anchor: string }[] {
  return (item.missed_topics ?? []).map((name) => {
    const topic = item.module.topics?.find((candidate) => withoutNumber(candidate.title) === withoutNumber(name));
    return {
      title: name.replace(/^\d+\.\s*/, ""),
      anchor: topic?.anchor ?? headingAnchor(topic?.title ?? name),
    };
  });
}

export type TopicChoice = "study" | "skim" | "skip";

// The section at the end of a module's page with its checkpoint, its project, or "mark it done".
export const CHECKPOINT_ANCHOR = "your-checkpoint";

// Where opening a module leads: a module to prove opens at its checkpoint, since proving it is taking the
// checkpoint, until it is finished; any other module opens at the top of its page.
export function openHref(item: PathItem, page: string | undefined): string | undefined {
  const progress = progressOf(item);
  const proving = item.choice === "prove" && progress !== "passed" && progress !== "done";
  return page && proving ? `${page}#${CHECKPOINT_ANCHOR}` : page;
}

// Every topic the learner takes (not skipped) is marked as finished: time to finish the module itself.
export function allTopicsFinished(item: PathItem): boolean {
  const finished = new Set(item.finished_topics ?? []);
  const kept = (item.module.topics ?? []).filter((topic) => topicChoiceOf(item, topic.title) !== "skip");
  return kept.length > 0 && kept.every((topic) => finished.has(topic.title));
}

// How the learner takes a topic of a module, by its title with or without the heading's number.
export function topicChoiceOf(item: PathItem, title: string): TopicChoice {
  if (item.choice !== "study") return "study";
  const bare = (name: string) => name.replace(/^\d+\.\s*/, "");
  if ((item.skip_topics ?? []).some((marked) => bare(marked.topic) === bare(title))) return "skip";
  if ((item.skim ?? []).some((marked) => bare(marked.topic) === bare(title))) return "skim";
  return "study";
}

