// Changes the learner makes to their path (a module's choice, a topic's, a topic finished) show at once: the server is far away, and waiting for each answer made every click take half a second. The requests
// go one after another, in the order made; the answer to the last one replaces the path shown. A refused change
// brings back the path the server has.
import { message, type PathApi } from "./api";
import type { Choice, LearningPath, TopicChoice } from "./model";
import { getPathState, handleSignedOut, setPath } from "./store";

// A module's or a topic's decision can be changed before signing in too: the draft, kept for a day, changes
// on the server, and signing up keeps it. Progress (a topic finished, a checkpoint) needs an account.
export function canChange(): boolean {
  const { account, draftId } = getPathState();
  return account !== null || draftId !== null;
}

export function sendChoice(api: PathApi, moduleId: string, choice: Choice): Promise<LearningPath> {
  const { account, draftId } = getPathState();
  return account || !draftId ? api.choose(moduleId, choice) : api.chooseInDraft(draftId, moduleId, choice);
}

export function sendTopicChoice(
  api: PathApi,
  moduleId: string,
  topic: string,
  choice: TopicChoice,
): Promise<LearningPath> {
  const { account, draftId } = getPathState();
  return account || !draftId
    ? api.chooseTopic(moduleId, topic, choice)
    : api.chooseTopicInDraft(draftId, moduleId, topic, choice);
}

let queue: Promise<unknown> = Promise.resolve();
let latest = 0;

export function changePath(
  api: PathApi,
  local: (path: LearningPath) => LearningPath,
  request: () => Promise<LearningPath>,
  onError: (text: string | null) => void,
): void {
  const current = getPathState().path;
  if (!current) return;
  onError(null);
  setPath(local(current));
  const ticket = ++latest;
  queue = queue.then(request).then(
    (answer) => {
      if (ticket === latest) setPath(answer);
    },
    async (reason: unknown) => {
      if (handleSignedOut(reason)) return;
      onError(message(reason));
      const session = await api.session().catch(() => null);
      if (session?.path && getPathState().account) setPath(session.path);
    },
  );
}

function withItem(path: LearningPath, moduleId: string, change: (item: LearningPath["items"][number]) => LearningPath["items"][number]): LearningPath {
  return { ...path, items: path.items.map((item) => (item.module.id === moduleId ? change(item) : item)) };
}

// What the API does with the change, so the page shows it before the answer arrives.
export function withChoice(path: LearningPath, moduleId: string, choice: Choice): LearningPath {
  return {
    ...withItem(path, moduleId, (item) => ({ ...item, choice })),
    proposals: path.proposals?.filter((proposal) => proposal.module_id !== moduleId),
  };
}

export function withTopic(path: LearningPath, moduleId: string, topic: string, choice: TopicChoice): LearningPath {
  return withItem(path, moduleId, (item) => {
    const order = (item.module.topics ?? []).map((candidate) => candidate.title);
    const kept = (marks: { topic: string; reason?: string | null; chosen?: boolean }[] | undefined, wanted: boolean, reason: string) => {
      const others = (marks ?? []).filter((marked) => marked.topic !== topic);
      if (wanted) others.push((marks ?? []).find((marked) => marked.topic === topic) ?? { topic, reason, chosen: true });
      return others.sort((a, b) => order.indexOf(a.topic) - order.indexOf(b.topic));
    };
    return {
      ...item,
      skim: kept(item.skim, choice === "skim", "You chose to skim it."),
      skip_topics: kept(item.skip_topics, choice === "skip", "You chose to skip it."),
      finished_topics: (item.finished_topics ?? []).filter((title) => !(title === topic && choice === "skip")),
    };
  });
}

export function withTopicFinished(path: LearningPath, moduleId: string, topic: string, finished: boolean): LearningPath {
  return withItem(path, moduleId, (item) => {
    const order = (item.module.topics ?? []).map((candidate) => candidate.title);
    const others = (item.finished_topics ?? []).filter((title) => title !== topic);
    if (finished) others.push(topic);
    return { ...item, finished_topics: others.sort((a, b) => order.indexOf(a) - order.indexOf(b)) };
  });
}
