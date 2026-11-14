// Calls to the Personalized Roadmap API. The model keys stay on that server; the site only sends the
// learner's answers. Its address comes from PERSONAL_PATH_API at build time (docusaurus.config.ts).
import { useMemo } from "react";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import type {
  CodingProblem,
  CheckpointQuestions,
  CheckpointSummary,
  Grade,
  LearningPath,
  Level,
  LevelAssessment,
  QuestionsResponse,
} from "./model";

export type Answers = Record<string, string>;

export interface ExampleProfile {
  id: string;
  title: string;
  answers: Answers;
}

export class ApiError extends Error {}

export interface PathApi {
  questions(): Promise<QuestionsResponse>;
  // Invented example learners a demo can start from.
  profiles(): Promise<ExampleProfile[]>;
  level(answers: Answers): Promise<LevelAssessment | null>;
  path(
    answers: Answers,
    level: Level | null,
    assessment: LevelAssessment | null,
  ): Promise<LearningPath>;
  // `version` is the path's curriculum version: a path keeps working after the course moves on.
  checkpoints(version: string): Promise<Record<string, CheckpointSummary>>;
  checkpoint(moduleId: string, attempt: number, version: string): Promise<CheckpointQuestions>;
  problem(moduleId: string, version: string): Promise<CodingProblem>;
  solved(path: LearningPath, moduleId: string): Promise<LearningPath>;
  confirm(path: LearningPath): Promise<LearningPath>;
  changeGoal(path: LearningPath, goal: string): Promise<LearningPath>;
  attempt(
    path: LearningPath,
    moduleId: string,
    attempt: number,
    answers: Record<string, number>,
  ): Promise<{ grade: Grade; path: LearningPath }>;
  // Marking done, and answering a suggestion, are rules of the path: the API applies them.
  act(
    action: "done" | "accept" | "decline",
    path: LearningPath,
    moduleId: string,
  ): Promise<LearningPath>;
}

export function usePathApi(): PathApi | null {
  const { siteConfig } = useDocusaurusContext();
  const base = siteConfig.customFields?.personalPathApi;
  // One client per address, so that components depending on it do not reload on every render.
  return useMemo(
    () => (typeof base === "string" && base ? pathApi(base) : null),
    [base],
  );
}

function pathApi(base: string): PathApi {
  const url = (path: string) => `${base.replace(/\/$/, "")}${path}`;

  async function call<T>(path: string, body?: unknown): Promise<T> {
    let response: Response;
    try {
      response = await fetch(url(path), {
        method: body === undefined ? "GET" : "POST",
        headers:
          body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(
        "The personal path service cannot be reached right now. Try again later.",
      );
    }
    if (!response.ok) {
      const detail = await response
        .json()
        .then((data) => (typeof data?.detail === "string" ? data.detail : null))
        .catch(() => null);
      throw new ApiError(
        detail ?? `The personal path service answered with an error (${response.status}).`,
      );
    }
    return (await response.json()) as T;
  }

  return {
    questions: () => call<QuestionsResponse>("/questions"),
    profiles: () => call<ExampleProfile[]>("/profiles"),
    level: async (answers) =>
      (await call<{ assessment: LevelAssessment | null }>("/level", { answers }))
        .assessment,
    path: (answers, level, assessment) =>
      call<LearningPath>("/path", { answers, level, assessment }),
    checkpoints: (version) =>
      call<Record<string, CheckpointSummary>>(`/checkpoints?version=${encodeURIComponent(version)}`),
    checkpoint: (moduleId, attempt, version) =>
      call<CheckpointQuestions>(
        `/checkpoints/${moduleId}?attempt=${attempt}&version=${encodeURIComponent(version)}`,
      ),
    problem: (moduleId, version) =>
      call<CodingProblem>(`/problems/${moduleId}?version=${encodeURIComponent(version)}`),
    solved: (path, moduleId) => call<LearningPath>(`/problems/${moduleId}/solved`, { path }),
    confirm: (path) => call<LearningPath>("/path/confirm", { path }),
    changeGoal: (path, goal) => call<LearningPath>("/path/goal", { path, goal }),
    attempt: (path, moduleId, attempt, answers) =>
      call<{ grade: Grade; path: LearningPath }>(`/attempts/${moduleId}`, {
        path,
        attempt,
        answers,
      }),
    act: (action, path, moduleId) =>
      call<LearningPath>(`/path/${action}`, { path, module_id: moduleId }),
  };
}
