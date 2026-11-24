// Calls to the Personalized Roadmap API. The model keys stay on that server; the site sends the learner's
// answers, and, once they sign in, every change to their path, which the API keeps. Its address comes from
// PERSONAL_PATH_API at build time (docusaurus.config.ts). The session is an HTTP-only cookie the API sets,
// so this code never sees it.
import { useMemo } from "react";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import { noteError } from "./pageErrors";
import type {
  Choice,
  CodingProblem,
  CheckpointQuestions,
  CheckpointSummary,
  Grade,
  LearningPath,
  Level,
  LevelAssessment,
  QuestionsResponse,
  Submission,
  TopicChoice,
} from "./model";

// Embedded in another site with a script tag (embed/), the panel cannot count on the API's cookie: browsers
// may block it on a site other than the API's. There the API hands the session to the panel, which keeps it
// and sends it with every request. On the course site this stays off and the cookie does the work.
export const embedding: {
  on: boolean;
  token: () => string | null;
  keep: (token: string | null) => void;
  // Opens the window where the school's designers change the panel's look; null for everyone else.
  design: (() => void) | null;
} = { on: false, token: () => null, keep: () => undefined, design: null };

// What the API said about the session, for the embedded panel: a new token, or none any more.
function keepToken(path: string, data: unknown): void {
  const found = data as { token?: unknown; account?: unknown } | null;
  if (typeof found?.token === "string") embedding.keep(found.token);
  else if (path === "/auth/sign-out" || path === "/auth/delete") embedding.keep(null);
  else if (path === "/auth/session" && found?.account === null) embedding.keep(null);
}

// A text question's answer, or a choice question's: the chosen options' ids and optional details.
export interface ChoiceAnswer {
  choices: string[];
  details: string;
}
export type Answer = string | ChoiceAnswer;
export type Answers = Record<string, Answer>;

export interface ExampleProfile {
  id: string;
  title: string;
  answers: Answers;
}

export interface Account {
  email: string;
  has_password: boolean; // false for an account made with Google
  reviewer: boolean; // may review submitted projects
}

export interface Session {
  account: Account | null;
  path: LearningPath | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

// Where learners who share their progress stop, per module in course order (reviewers only).
export interface ModuleReport {
  module_id: string;
  title: string;
  included: number; // shared paths that study or prove the module
  finished: number;
  failed_once: number; // paths with at least one failed checkpoint attempt
  stopped_here: number; // paths whose first unfinished module is this one
}

export interface CourseReport {
  curriculum_version: string;
  paths: number;
  modules: ModuleReport[];
}

// A learner's report of a checkpoint question, and the same report as reviewers see it.
export type ReportReason = "wrong_answer" | "unclear" | "off_topic" | "wrong_mark" | "other";

export interface ReportedQuestion {
  id: string;
  module_id: string;
  module_title: string;
  curriculum_version: string;
  question_id: string;
  reason: ReportReason;
  comment: string;
  reported_at: string;
  resolved: boolean;
  question: {
    id: string;
    topic: string;
    text: string;
    options: string[];
    answer: number;
    explanation: string;
  } | null;
  // Instead, for an open question: its rubric and full answer.
  open_question?: {
    id: string;
    topic: string;
    text: string;
    rubric: string[];
    required: number;
    model_answer: string;
  } | null;
}

// A question of the attempt the learner passed, with the right option and why.
export interface PassedQuestion {
  id: string;
  topic: string;
  text: string;
  options: string[];
  answer: number | null; // none for an open question
  explanation: string; // for an open question, a full answer
  kind?: "choice" | "open";
}

export type ModuleAction = "done" | "accept" | "decline";

// What a learner's public link shows: never their email, answers or reasons.
export interface ProvenModule {
  title: string;
  url: string;
  // checkpoint: graded questions and the coding problem; questions: the coding problem not yet;
  // project: accepted by a reviewer; marked_done: a module without a checkpoint, on the learner's word.
  how: "checkpoint" | "questions" | "project" | "marked_done";
  score: string | null;
  attempts: number;
}

export interface PublicProgress {
  title: string | null;
  level: Level | null;
  modules_in_path: number;
  finished: ProvenModule[];
  curriculum: { version: string; site_version: string | null; title: string; licence: string };
  attribution_url: string;
}

// A turn of the conversation with the assistant in the path panel.
export interface ChatTurn {
  speaker: "learner" | "assistant";
  text: string;
}

export interface ChatReply {
  reply: string;
  modules: { id: string; title: string }[]; // the path's modules the reply talks about
}

export interface PathApi {
  questions(): Promise<QuestionsResponse>;
  // Invented example learners a demo can start from.
  profiles(): Promise<ExampleProfile[]>;
  level(answers: Answers): Promise<LevelAssessment | null>;
  // Signed in, the path becomes the account's path; otherwise it is a draft kept for a day under draft_id.
  plan(
    answers: Answers,
    level: Level | null,
    assessment: LevelAssessment | null,
  ): Promise<{ path: LearningPath; draft_id: string | null }>;
  draft(draftId: string): Promise<LearningPath>;

  session(): Promise<Session>;
  signUp(email: string, password: string, draftId: string | null): Promise<Session>;
  signIn(email: string, password: string, draftId: string | null): Promise<Session>;
  signOut(): Promise<Session>;
  // The password, or for an account made with Google, its email address.
  deleteAccount(confirmation: string): Promise<Session>;
  // Other ways to sign in that the API offers.
  providers(): Promise<{ google: boolean }>;
  // Where to send the browser to sign in with Google; it comes back to `returnTo` signed in.
  googleSignIn(returnTo: string, draftId: string | null): string;
  // The API's page that ends a Google sign-in started from the embedded panel, in a window of its own.
  embedSignedInPage(): string;

  // The signed-in learner's path. Every change returns the path as the API stored it.
  choose(moduleId: string, choice: Choice): Promise<LearningPath>;
  // A topic of a module the learner studies: to study in full, to skim, or to skip out of the checkpoint.
  chooseTopic(moduleId: string, topic: string, choice: TopicChoice): Promise<LearningPath>;
  finishTopic(moduleId: string, topic: string, finished: boolean): Promise<LearningPath>;
  confirm(): Promise<LearningPath>;
  share(on: boolean): Promise<LearningPath>;
  // A read-only link to what the learner finished; a new one replaces the old.
  publicLink(): Promise<string | null>;
  newPublicLink(): Promise<string>;
  removePublicLink(): Promise<void>;
  publicProgress(token: string): Promise<PublicProgress>;
  changeGoal(goal: string): Promise<LearningPath>;
  reset(): Promise<void>;
  // `topic` names a suggestion about one of the module's topics, to accept or decline.
  act(action: ModuleAction, moduleId: string, topic?: string | null): Promise<LearningPath>;
  attempt(
    moduleId: string,
    attempt: number,
    answers: Record<string, number>,
    openAnswers?: Record<string, string>,
  ): Promise<{ grade: Grade; path: LearningPath }>;
  solved(moduleId: string): Promise<LearningPath>;
  // A question about the path, or about the module page the learner is reading.
  chat(
    question: string,
    history: ChatTurn[],
    moduleId: string | null,
    section?: string | null,
    attached?: { code: string; error: string } | null,
    pageError?: string | null,
  ): Promise<ChatReply>;

  // Projects: the learner's submission for a module, and, for reviewers, the queue.
  submit(moduleId: string, form: FormData): Promise<Submission>;
  mySubmission(moduleId: string): Promise<Submission | null>;
  archiveUrl(submissionId: string): string;
  // The archive as a download, for the embedded panel, whose links do not carry the session.
  downloadArchive(submissionId: string, fileName: string): Promise<void>;
  reviewQueue(): Promise<{ waiting: Submission[]; reviewed: Submission[] }>;
  review(submissionId: string, accept: boolean, comment: string): Promise<Submission>;
  courseReport(): Promise<CourseReport>;
  reportQuestion(moduleId: string, questionId: string, reason: ReportReason, comment: string): Promise<unknown>;
  questionReports(): Promise<ReportedQuestion[]>;
  resolveQuestionReport(reportId: string, resolved: boolean): Promise<unknown>;

  // `version` is the path's curriculum version: a path keeps working after the course moves on.
  checkpoints(version: string): Promise<Record<string, CheckpointSummary>>;
  checkpoint(moduleId: string, attempt: number, version: string): Promise<CheckpointQuestions>;
  problem(moduleId: string, version: string): Promise<CodingProblem>;
  passedQuestions(moduleId: string): Promise<PassedQuestion[]>;
}

export function usePathApi(): PathApi | null {
  const { siteConfig } = useDocusaurusContext();
  const base = siteConfig.customFields?.personalPathApi;
  // One client per address, so that components depending on it do not reload on every render.
  return useMemo(() => (typeof base === "string" && base ? pathApi(base) : null), [base]);
}

const clients = new Map<string, PathApi>();

export function pathApi(base: string): PathApi {
  const known = clients.get(base);
  if (known) return known;
  const url = (path: string) => `${base.replace(/\/$/, "")}${path}`;
  const version = (value: string) => `version=${encodeURIComponent(value)}`;

  // A form sets its own type, with the boundary between its parts.
  function headersFor(json: boolean): Record<string, string> | undefined {
    const headers: Record<string, string> = {};
    if (json) headers["Content-Type"] = "application/json";
    if (embedding.on) {
      headers["X-DotPath-Embed"] = "1";
      const token = embedding.token();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    return Object.keys(headers).length ? headers : undefined;
  }

  async function call<T>(path: string, body?: unknown): Promise<T> {
    let response: Response;
    const form = body instanceof FormData;
    try {
      response = await fetch(url(path), {
        method: body === undefined ? "GET" : "POST",
        credentials: "include",
        headers: headersFor(body !== undefined && !form),
        body: body === undefined ? undefined : form ? body : JSON.stringify(body),
      });
    } catch {
      const unreachable = "The personal path service cannot be reached right now. Try again later.";
      noteError(unreachable);
      throw new ApiError(unreachable, 0);
    }
    if (!response.ok) {
      const detail = await response
        .json()
        .then((data) => (typeof data?.detail === "string" ? data.detail : null))
        .catch(() => null);
      const text = detail ?? `The personal path service answered with an error (${response.status}).`;
      // What the learner saw, for the assistant; not the assistant's own errors, nor a lapsed sign-in.
      if (path !== "/me/chat" && response.status !== 401) noteError(text);
      // A lapsed session: the embedded panel forgets its token (a wrong password is not one).
      if (embedding.on && response.status === 401 && !path.startsWith("/auth/")) embedding.keep(null);
      throw new ApiError(text, response.status);
    }
    const data = (await response.json()) as T;
    if (embedding.on) keepToken(path, data);
    return data;
  }

  const client: PathApi = {
    questions: () => call("/questions"),
    profiles: () => call("/profiles"),
    level: async (answers) =>
      (
        await call<{ assessment: LevelAssessment | null }>("/level", {
          answers,
        })
      ).assessment,
    plan: (answers, level, assessment) => call("/path", { answers, level, assessment }),
    draft: (draftId) => call(`/drafts/${encodeURIComponent(draftId)}`),

    session: () => call("/auth/session"),
    signUp: (email, password, draftId) => call("/auth/sign-up", { email, password, draft_id: draftId }),
    signIn: (email, password, draftId) => call("/auth/sign-in", { email, password, draft_id: draftId }),
    signOut: () => call("/auth/sign-out", {}),
    deleteAccount: (confirmation) => call("/auth/delete", { confirmation }),
    providers: () => call("/auth/providers"),
    googleSignIn: (returnTo, draftId) =>
      url(
        `/auth/google?${new URLSearchParams({
          return_to: returnTo,
          ...(draftId ? { draft_id: draftId } : {}),
        })}`,
      ),

    embedSignedInPage: () =>
      url(`/embed/signed-in?origin=${encodeURIComponent(window.location.origin)}`),

    choose: (moduleId, choice) => call("/me/path/choice", { module_id: moduleId, choice }),
    chooseTopic: (moduleId, topic, choice) => call("/me/path/topic", { module_id: moduleId, topic, choice }),
    finishTopic: (moduleId, topic, finished) =>
      call("/me/path/topic-finished", { module_id: moduleId, topic, finished }),
    confirm: () => call("/me/path/confirm", {}),
    share: (on) => call("/me/path/share", { share: on }),
    publicLink: async () => (await call<{ token: string | null }>("/me/public-link")).token,
    newPublicLink: async () => (await call<{ token: string }>("/me/public-link", {})).token,
    removePublicLink: async () => {
      await call("/me/public-link/remove", {});
    },
    publicProgress: (token) => call(`/public/${encodeURIComponent(token)}`),
    changeGoal: (goal) => call("/me/path/goal", { goal }),
    reset: async () => {
      await call("/me/path/reset", {});
    },
    act: (action, moduleId, topic) => call(`/me/path/${action}`, { module_id: moduleId, topic: topic ?? null }),
    attempt: (moduleId, attempt, answers, openAnswers = {}) =>
      call(`/me/attempts/${moduleId}`, { attempt, answers, open_answers: openAnswers }),
    solved: (moduleId) => call(`/me/problems/${moduleId}/solved`, {}),
    chat: (question, history, moduleId, section, attached, pageError) =>
      call("/me/chat", {
        question,
        history,
        module_id: moduleId,
        section: section ?? null,
        code: attached?.code ?? null,
        error: attached?.error ?? null,
        page_error: pageError ?? null,
      }),

    submit: (moduleId, form) => call(`/me/submissions/${moduleId}`, form),
    mySubmission: (moduleId) => call(`/me/submissions/${moduleId}`),
    archiveUrl: (submissionId) => url(`/submissions/${encodeURIComponent(submissionId)}/archive`),
    downloadArchive: async (submissionId, fileName) => {
      const response = await fetch(url(`/submissions/${encodeURIComponent(submissionId)}/archive`), {
        credentials: "include",
        headers: headersFor(false),
      });
      if (!response.ok) throw new ApiError("The archive could not be downloaded.", response.status);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(await response.blob());
      link.download = fileName;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
    },
    reviewQueue: () => call("/review/submissions"),
    courseReport: () => call("/review/report"),
    reportQuestion: (moduleId, questionId, reason, comment) =>
      call(`/me/checkpoints/${moduleId}/reports`, { question_id: questionId, reason, comment }),
    questionReports: () => call("/review/question-reports"),
    resolveQuestionReport: (reportId, resolved) =>
      call(`/review/question-reports/${encodeURIComponent(reportId)}`, { resolved }),
    review: (submissionId, accept, comment) =>
      call(`/review/submissions/${encodeURIComponent(submissionId)}`, {
        accept,
        comment,
      }),

    checkpoints: (v) => call(`/checkpoints?${version(v)}`),
    checkpoint: (moduleId, attempt, v) => call(`/checkpoints/${moduleId}?attempt=${attempt}&${version(v)}`),
    problem: (moduleId, v) => call(`/problems/${moduleId}?${version(v)}`),
    passedQuestions: (moduleId) => call(`/me/checkpoints/${moduleId}/passed`),
  };
  clients.set(base, client);
  return client;
}

const GOOGLE_ERRORS: Record<string, string> = {
  cancelled: "Signing in with Google was cancelled.",
  google: "Google could not confirm your account. Try again, or use your email and a password.",
};

// Google sign-in from the embedded panel: in a window of its own, so the learner stays on the school's page.
// The API's page at the end of it hands over a session, to this site only; the panel then reads the session.
export function signInWithGoogleWindow(api: PathApi, draftId: string | null): Promise<Session> {
  const start = api.googleSignIn(api.embedSignedInPage(), draftId);
  const popup = window.open(start, "dotpath-google", "popup,width=480,height=640");
  if (!popup) return Promise.reject(new ApiError("Allow pop-ups for this site to sign in with Google.", 0));
  const apiOrigin = new URL(start).origin;
  return new Promise<Session>((resolve, reject) => {
    let settled = false;
    const finish = (then: () => void) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("message", onMessage);
      window.clearInterval(watch);
      then();
    };
    function onMessage(event: MessageEvent) {
      if (event.origin !== apiOrigin || event.data?.type !== "dotpath-session") return;
      const { token, error } = event.data as { token?: string; error?: string };
      finish(() => {
        if (!token) return reject(new ApiError(GOOGLE_ERRORS[error ?? ""] ?? GOOGLE_ERRORS.google, 0));
        embedding.keep(token);
        api.session().then(resolve, reject);
      });
    }
    window.addEventListener("message", onMessage);
    // Closed without an answer: give a message on its way a moment, then call it cancelled.
    const watch = window.setInterval(() => {
      if (!popup.closed) return;
      window.clearInterval(watch);
      window.setTimeout(() => finish(() => reject(new ApiError(GOOGLE_ERRORS.cancelled, 0))), 1000);
    }, 400);
  });
}

export function message(reason: unknown): string {
  return reason instanceof ApiError ? reason.message : "Something went wrong. Try again later.";
}
