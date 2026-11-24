// For the course team: per module, how many learners' paths include it, finish it, fail its checkpoint
// and stop at it. Only learners who turned on "share my progress" are counted, and nothing identifies them.
import React, { useEffect, useState, type ReactNode } from "react";
import { message, usePathApi, type CourseReport as Report, type ModuleReport } from "./api";
import { openAuth, usePathState } from "./store";
import { Spinner } from "./ui";
import styles from "./path.module.css";
import report from "./report.module.css";

const FEW = 5; // below this many learners, the numbers are examples, not a pattern

export default function CourseReport(): ReactNode {
  const api = usePathApi();
  const { ready, account } = usePathState();
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api || !account?.reviewer) return;
    setError(null);
    api
      .courseReport()
      .then(setData)
      .catch((reason: unknown) => setError(message(reason)));
  }, [api, account?.email, account?.reviewer]);

  if (!api || !ready)
    return (
      <p className={styles.muted}>
        <Spinner /> Loading…
      </p>
    );
  if (!account)
    return (
      <div className={styles.card}>
        <p>Sign in with a course team account to see where learners stop.</p>
        <button type="button" className={styles.primary} onClick={() => openAuth("sign-in")}>
          Sign in
        </button>
      </div>
    );
  if (!account.reviewer) return <p className={styles.error}>This account is not on the course team.</p>;

  return (
    <div className={styles.ppRoot}>
      <div className={`${styles.pathPage} ${report.page}`}>
        <header>
          <span className={styles.eyebrow}>For the course team</span>
          <h1>Where learners stop</h1>
          <p className={styles.muted}>
            Counted from learners who turned on “share my progress”. A learner “stopped” at the first module of
            their path they have not finished. Nothing here identifies a learner: no answers, levels or emails.
          </p>
        </header>
        {error && <p className={styles.error}>{error}</p>}
        {!data && !error && (
          <p className={styles.muted}>
            <Spinner /> Loading…
          </p>
        )}
        {data && (
          <div className={report.body}>
            <Body data={data} />
          </div>
        )}
      </div>
    </div>
  );
}

function Body({ data }: { data: Report }): ReactNode {
  const rows = data.modules.filter((row) => row.included > 0);
  if (data.paths === 0 || rows.length === 0)
    return (
      <div className={styles.card}>
        <p>No learner shares their progress on this version of the course yet.</p>
      </div>
    );

  const top = (key: (row: ModuleReport) => number) =>
    rows.reduce((best, row) => (key(row) > key(best) ? row : best), rows[0]);
  const stop = top((row) => row.stopped_here);
  // Every module where the most learners stopped, not only the first of them.
  const mostStopped = rows.filter((row) => stop.stopped_here > 0 && row.stopped_here === stop.stopped_here);
  const shortTitle = (row: ModuleReport) => row.title.split(" › ").slice(-1)[0];
  const fail = top((row) => (row.included ? row.failed_once / row.included : 0));
  const finishedAll = data.paths - rows.reduce((sum, row) => sum + row.stopped_here, 0);
  const maxStopped = Math.max(...rows.map((row) => row.stopped_here), 1);

  return (
    <>
      {data.paths < FEW && (
        <p className={report.note}>
          Only {data.paths} {data.paths === 1 ? "learner shares" : "learners share"} their progress: read these
          numbers as examples, not as a pattern.
        </p>
      )}
      <div className={report.tiles}>
        <Tile value={data.paths} label="learners sharing progress" />
        <Tile value={finishedAll} label="finished every module on their path" />
        <Tile
          value={stop.stopped_here}
          label={
            !stop.stopped_here
              ? "stopped anywhere"
              : mostStopped.length === 1
                ? `the most stopped at one module: ${stop.title}`
                : `stopped at each of ${mostStopped.length} modules, the most at any one: ${mostStopped
                    .map(shortTitle)
                    .join(", ")}`
          }
          alert={stop.stopped_here > 0}
        />
        <Tile
          value={fail.failed_once ? `${Math.round((fail.failed_once / fail.included) * 100)}%` : "0%"}
          label={fail.failed_once ? `failed the checkpoint of ${fail.title} at least once` : "failed a checkpoint"}
          alert={fail.failed_once > 0}
        />
      </div>

      <section className={styles.section}>
        <h2>
          By module, in course order{" "}
          <span className={styles.muted} title={data.curriculum_version}>
            version {data.curriculum_version.slice(0, 7)}
          </span>
        </h2>
        <div className={report.scroll}>
          <table className={report.table}>
            <thead>
              <tr>
                <th scope="col">Module</th>
                <th scope="col" title="Paths that study or prove the module">
                  On paths
                </th>
                <th scope="col">Finished</th>
                <th scope="col" title="Paths with at least one failed checkpoint attempt">
                  Failed once
                </th>
                <th scope="col" title="Paths whose first unfinished module is this one">
                  Stopped here
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.module_id} className={mostStopped.includes(row) ? report.worst : undefined}>
                  <th scope="row">{row.title}</th>
                  <td>{row.included}</td>
                  <td>
                    <Share part={row.finished} whole={row.included} />
                  </td>
                  <td className={row.failed_once ? report.warn : undefined}>{row.failed_once}</td>
                  <td>
                    <span className={report.stopCell}>
                      <span
                        className={report.stopBar}
                        style={{ width: `${(row.stopped_here / maxStopped) * 100}%` }}
                        aria-hidden
                      />
                      <span>{row.stopped_here}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={`${styles.muted} ${report.after}`}>
          Modules no shared path includes are left out. A high “failed once” with a high “stopped here” points at a
          module, or a checkpoint, worth looking at first.
        </p>
      </section>
    </>
  );
}

function Tile({ value, label, alert = false }: { value: ReactNode; label: string; alert?: boolean }): ReactNode {
  return (
    <div className={`${report.tile} ${alert ? report.tileAlert : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Share({ part, whole }: { part: number; whole: number }): ReactNode {
  const percent = whole ? Math.round((part / whole) * 100) : 0;
  return (
    <span className={report.share}>
      <span className={report.track} aria-hidden>
        <span className={report.fill} style={{ width: `${percent}%` }} />
      </span>
      <span>
        {part} <span className={styles.muted}>({percent}%)</span>
      </span>
    </span>
  );
}
