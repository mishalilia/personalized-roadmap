// The page behind a learner's public link: their path's goal and level and what they finished. Anyone with the
// link can open it; it shows nothing private (no email, answers or reasons), and the learner can remove it.
import React, { useEffect, useState, type ReactNode } from "react";
import { BadgeCheck, CircleCheck, Code, FolderCheck } from "lucide-react";
import { message, usePathApi, type ProvenModule, type PublicProgress as Progress } from "./api";
import { Spinner } from "./ui";
import styles from "./path.module.css";
import report from "./report.module.css";
import own from "./public.module.css";

const HOW: Record<ProvenModule["how"], { label: string; icon: ReactNode; proof: string }> = {
  checkpoint: {
    label: "Checkpoint passed",
    icon: <BadgeCheck size={18} aria-hidden />,
    proof: "Questions graded by the server, and the coding problem solved where the module has one.",
  },
  questions: {
    label: "Questions passed",
    icon: <Code size={18} aria-hidden />,
    proof: "Questions graded by the server; the module's coding problem is not solved yet.",
  },
  project: {
    label: "Project accepted",
    icon: <FolderCheck size={18} aria-hidden />,
    proof: "A submitted project, accepted by a reviewer.",
  },
  marked_done: {
    label: "Marked done",
    icon: <CircleCheck size={18} aria-hidden />,
    proof: "A module without a checkpoint, marked done by the learner.",
  },
};

export default function PublicProgress(): ReactNode {
  const api = usePathApi();
  const [data, setData] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const token = new URLSearchParams(window.location.search).get("link");

  useEffect(() => {
    if (!api || !token) return;
    api.publicProgress(token).then(setData, (reason) => setError(message(reason)));
  }, [api, token]);

  let body: ReactNode;
  if (!api) body = <p className={styles.error}>Personal paths are not set up on this site.</p>;
  else if (!token) body = <p className={styles.error}>This address has no link in it.</p>;
  else if (error) body = <p className={styles.error}>{error}</p>;
  else if (!data)
    body = (
      <p className={styles.muted}>
        <Spinner /> Loading…
      </p>
    );
  else body = <Body data={data} />;

  return (
    <div className={styles.ppRoot}>
      <div className={`${styles.pathPage} ${report.page}`}>
        <header>
          <span className={styles.eyebrow}>Learning progress</span>
          <h1>{data?.title ?? "Personal learning path"}</h1>
          {data && (
            <p className={styles.muted}>
              On {data.curriculum.title}
              {data.level ? `, planned for the ${data.level} level` : ""}.
            </p>
          )}
        </header>
        <div className={report.body}>{body}</div>
      </div>
    </div>
  );
}

function Body({ data }: { data: Progress }): ReactNode {
  const graded = data.finished.filter((m) => m.how !== "marked_done").length;
  return (
    <>
      <div className={report.tiles}>
        <Tile
          value={`${data.finished.length} of ${data.modules_in_path}`}
          label="modules of the path finished"
        />
        <Tile value={graded} label="checked by a checkpoint or a reviewer" />
      </div>
      {data.finished.length === 0 ? (
        <div className={styles.card}>
          <p>Nothing finished yet.</p>
        </div>
      ) : (
        <ul className={own.list}>
          {data.finished.map((module) => {
            const how = HOW[module.how];
            return (
              <li key={module.url + module.title} className={own.row} data-how={module.how}>
                <span className={own.icon} title={how.proof}>
                  {how.icon}
                </span>
                <span className={own.title}>
                  <a href={module.url} target="_blank" rel="noreferrer">
                    {module.title}
                  </a>
                  <span className={styles.muted}>{how.label}</span>
                </span>
                {module.score && (
                  <span className={own.score} title={`Passed on attempt ${module.attempts}`}>
                    {module.score}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className={`${styles.muted} ${own.note}`}>
        Checkpoints are questions generated from each module and graded on the server; coding problems are
        checked against tests in the learner's browser. Course content:{" "}
        <a href={data.attribution_url} target="_blank" rel="noreferrer">
          {data.curriculum.title}
        </a>
        , {data.curriculum.licence}.
      </p>
    </>
  );
}

function Tile({ value, label }: { value: ReactNode; label: string }): ReactNode {
  return (
    <div className={report.tile}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
