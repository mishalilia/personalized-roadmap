// Every topic of a module the learner studies, each with a link to its section and its own switch: read it in
// full, skim it, or skip it out of the checkpoint. The learner decides it here, so the path stays confirmed.
// Once the path is confirmed, a box before each topic marks it as finished: the learner's own tally.
import React, { useState, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import { ArrowRight } from "lucide-react";
import { usePathApi } from "./api";
import {
  CHECKPOINT_ANCHOR,
  allTopicsFinished,
  headingAnchor,
  topicChoiceOf,
  type PathItem,
  type TopicChoice,
} from "./model";
import { openAuth, usePathState } from "./store";
import { changePath, withTopic, withTopicFinished } from "./changes";
import { Reveal } from "./ui";
import styles from "./path.module.css";

const TOPIC_LABEL: Record<TopicChoice, string> = { study: "Study", skim: "Skim", skip: "Skip" };
const TOPIC_HINT: Record<TopicChoice, string> = {
  study: "Read it in full",
  skim: "Go through it quickly; the checkpoint still asks about it",
  skip: "You know it: leave it out, and the checkpoint does not ask about it",
};

const bare = (title: string) => title.replace(/^\d+\.\s*/, "");

export default function ModuleTopics({
  item,
  page,
  hasCheckpoint = false,
  passed = false,
}: {
  item: PathItem;
  page?: string;
  hasCheckpoint?: boolean;
  passed?: boolean; // the module is finished: every topic it kept counts as finished, and nothing is changed here
}): ReactNode {
  const api = usePathApi();
  const { account, path } = usePathState();
  const [error, setError] = useState<string | null>(null);
  const topics = item.module.topics ?? [];
  if (item.choice !== "study" || item.module.is_project || topics.length < 2) return null;
  const confirmed = Boolean(path?.confirmed_at);
  const finished = new Set(
    passed
      ? topics.filter((topic) => topicChoiceOf(item, topic.title) !== "skip").map((topic) => topic.title)
      : (item.finished_topics ?? []),
  );
  const kept = topics.filter((topic) => topicChoiceOf(item, topic.title) !== "skip");
  const finishedCount = kept.filter((topic) => finished.has(topic.title)).length;
  const reasonOf = (title: string) =>
    [...(item.skip_topics ?? []), ...(item.skim ?? [])].find((marked) => bare(marked.topic) === bare(title));

  function choose(title: string, choice: TopicChoice) {
    if (!api) return;
    if (!account) return openAuth("sign-up", "Create an account to change and keep your path.");
    changePath(
      api,
      (current) => withTopic(current, item.module.id, title, choice),
      () => api.chooseTopic(item.module.id, title, choice),
      setError,
    );
  }

  function finish(title: string, done: boolean) {
    if (!api) return;
    changePath(
      api,
      (current) => withTopicFinished(current, item.module.id, title, done),
      () => api.finishTopic(item.module.id, title, done),
      setError,
    );
  }

  return (
    <div className={styles.moduleTopics}>
      <span className={styles.moduleTopicsHead}>
        Topics
        {confirmed && kept.length > 0 && (
          <span className={styles.moduleTopicsCount}>
            {finishedCount} of {kept.length} finished
          </span>
        )}
      </span>
      <ul>
        {topics.map((topic) => {
          const current = topicChoiceOf(item, topic.title);
          const marked = current !== "study" ? reasonOf(topic.title) : undefined;
          const anchor = topic.anchor ?? headingAnchor(topic.title);
          return (
            <li key={topic.title} data-choice={current} data-finished={finished.has(topic.title)}>
              <div className={styles.moduleTopicRow}>
                {confirmed ? (
                  <label className={styles.moduleTopicTitle}>
                    {/* A skipped topic is not one to finish: its box fades out instead of vanishing. */}
                    <input
                      type="checkbox"
                      className={styles.topicDone}
                      data-hidden={current === "skip"}
                      tabIndex={current === "skip" ? -1 : undefined}
                      checked={finished.has(topic.title)}
                      disabled={passed || current === "skip"}
                      onChange={(event) => finish(topic.title, event.target.checked)}
                      aria-label={`${bare(topic.title)}: finished`}
                    />
                    <span>{bare(topic.title)}</span>
                  </label>
                ) : (
                  <span className={styles.moduleTopicTitle}>{bare(topic.title)}</span>
                )}
                {!passed && (
                <div className={styles.topicSwitch} role="radiogroup" aria-label={`${bare(topic.title)}: how to read it`}>
                  {(["study", "skim", "skip"] as const).map((choice) => (
                    <button
                      key={choice}
                      type="button"
                      role="radio"
                      aria-checked={current === choice}
                      data-choice={choice}
                      title={TOPIC_HINT[choice]}
                      onClick={() => current !== choice && choose(topic.title, choice)}
                    >
                      {TOPIC_LABEL[choice]}
                    </button>
                  ))}
                </div>
                )}
                {page ? (
                  <Link to={`${page}#${anchor}`} className={styles.topicGo} aria-label={`Open ${bare(topic.title)}`}>
                    Open <ArrowRight size={13} aria-hidden />
                  </Link>
                ) : (
                  <a href={`#${anchor}`} className={styles.topicGo} aria-label={`Go to ${bare(topic.title)}`}>
                    Go <ArrowRight size={13} aria-hidden />
                  </a>
                )}
              </div>
              {marked && !marked.chosen && <small>{marked.reason}</small>}
            </li>
          );
        })}
      </ul>
      <Reveal show={confirmed && !passed && allTopicsFinished(item)}>
        <p className={styles.topicsAllDone} role="status">
          <span>
            {hasCheckpoint
              ? "Every topic is finished: time for the checkpoint."
              : "Every topic is finished: mark the module done."}
          </span>
          {page ? (
            <Link to={`${page}#${CHECKPOINT_ANCHOR}`} className={styles.primarySm}>
              {hasCheckpoint ? "Take the checkpoint" : "Finish the module"} <ArrowRight size={13} aria-hidden />
            </Link>
          ) : (
            <a href={`#${CHECKPOINT_ANCHOR}`} className={styles.primarySm}>
              {hasCheckpoint ? "Take the checkpoint" : "Finish the module"} <ArrowRight size={13} aria-hidden />
            </a>
          )}
        </p>
      </Reveal>
      {!passed && (
        <small className={styles.moduleTopicsNote}>
          Skim: the checkpoint still asks about the topic. Skip: the checkpoint leaves it out.
        </small>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
