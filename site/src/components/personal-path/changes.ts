// Changes the learner makes to their signed-in path (a module's choice, a topic's, a topic finished) show at
// once: the server is far away, and waiting for each answer made every click take half a second. The requests
// go one after another, in the order made; the answer to the last one replaces the path shown. A refused change
// brings back the path the server has.
import { message, type PathApi } from "./api";
import type { Choice, LearningPath, TopicChoice } from "./model";
import { getPathState, handleSignedOut, setPath } from "./store";

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
export function withChoice(path: LearningPath, moduleId: string, choice: Choice, keepConfirmed = false): LearningPath {
  return {
    ...withItem(path, moduleId, (item) => ({ ...item, choice })),
    confirmed_at: keepConfirmed ? path.confirmed_at : null,
    proposals: path.proposals?.filter((proposal) => proposal.module_id !== moduleId),
  };
}

export function withTopic(path: LearningPath, moduleId: string, topic: string, choice: TopicChoice): LearningPath {
  return withItem(path, moduleId, (item) => {
    const order = (item.module.topics ?? []).map((candidate) => candidate.title);
    const kept = (marks: { topic: string; reason: string; chosen?: boolean }[] | undefined, wanted: boolean, reason: string) => {
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
