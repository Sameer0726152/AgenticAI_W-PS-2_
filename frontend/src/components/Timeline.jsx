import { useEffect, useState } from "react";
import { api } from "../api.js";
import { formatTime } from "../useLatestRun.js";

export default function Timeline({ repoId, refreshKey }) {
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    if (repoId) api.listRuns(repoId).then(setRuns).catch(() => {});
  }, [repoId, refreshKey]);

  if (!runs.length) return null;
  return (
    <section className="card table-wrap">
      <h2>Assessment timeline</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Commit</th>
            <th>Trigger</th>
            <th>Changed files</th>
            <th>Re-checked</th>
            <th>Status changes</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                #{r.id}
                <div className="muted">{formatTime(r.finished_at || r.started_at)}</div>
              </td>
              <td>
                <span className="mono">{r.commit_sha.slice(0, 7)}</span>
                <div className="muted">{r.commit_message}</div>
              </td>
              <td>
                <span className="pill">{r.trigger}</span>
                {r.status !== "done" && <div className={r.status === "failed" ? "error" : "muted"}>{r.status}</div>}
              </td>
              <td className="mono small-text">{r.changed_files.map((f) => f.path).join(", ") || "—"}</td>
              <td className="small-text">{r.affected_skills.length || "—"}</td>
              <td className="small-text">
                {r.changes.length
                  ? r.changes.map((c) => `${c.skill_label}: ${c.from_status} → ${c.to_status}`).join("; ")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
