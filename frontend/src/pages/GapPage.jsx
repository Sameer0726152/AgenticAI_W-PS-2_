import { useEffect, useState } from "react";
import { api } from "../api.js";
import EvidenceList from "../components/EvidenceList.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { formatTime, useLatestRun } from "../useLatestRun.js";

function SummaryTile({ label, demonstrated, partial, total }) {
  return (
    <div className="tile">
      <div className="tile-value">
        {demonstrated} / {total}
      </div>
      <div className="muted">{label} demonstrated</div>
      {partial > 0 && <div className="muted">+{partial} partially</div>}
    </div>
  );
}

export default function GapPage() {
  const [jobs, setJobs] = useState([]);
  const [repos, setRepos] = useState([]);
  const [jobId, setJobId] = useState(null);
  const [repoId, setRepoId] = useState(null);
  const [gaps, setGaps] = useState(null);
  const [error, setError] = useState(null);
  const { latest } = useLatestRun(repoId);

  useEffect(() => {
    Promise.all([api.listJobs(), api.listRepos()])
      .then(([js, rs]) => {
        setJobs(js);
        setRepos(rs);
        if (js.length) setJobId(js[0].id);
        if (rs.length) setRepoId(rs[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  // Reload whenever the selection changes or a new assessment finishes.
  useEffect(() => {
    if (!jobId || !repoId) return;
    api
      .gaps(repoId, jobId)
      .then((g) => {
        setGaps(g);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [jobId, repoId, latest.run_id, latest.status]);

  if (!jobs.length || !repos.length) {
    return <p className="muted stack">Add a job (Jobs tab) and connect a repository (Repository tab) first.</p>;
  }

  const missingRequired = gaps?.rows.filter((r) => r.importance === "required" && r.status === "not_demonstrated") ?? [];

  return (
    <div className="stack">
      <section className="card">
        <div className="row-form">
          <label className="field">
            Job
            <select value={jobId ?? ""} onChange={(e) => setJobId(Number(e.target.value))}>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.company}: {j.title}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Repository
            <select value={repoId ?? ""} onChange={(e) => setRepoId(Number(e.target.value))}>
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error && <p className="error">{error}</p>}

        {gaps && (
          <>
            <p className="muted">
              Job source:{" "}
              <a href={gaps.job.source_url} target="_blank" rel="noreferrer">
                {gaps.job.source_url}
              </a>
              <br />
              {gaps.run_id ? (
                <>
                  Based on assessment run #{gaps.run_id} of commit{" "}
                  <span className="mono">{gaps.commit_sha.slice(0, 7)}</span> “{gaps.commit_message}” (
                  {formatTime(gaps.assessed_at)})
                  {latest.status === "running" && <strong> · a new assessment is running…</strong>}
                </>
              ) : (
                "This repository has not been assessed yet."
              )}
            </p>
            <div className="tiles">
              <SummaryTile
                label="Required"
                demonstrated={gaps.summary.required_demonstrated}
                partial={gaps.summary.required_partial}
                total={gaps.summary.required_total}
              />
              <SummaryTile
                label="Preferred"
                demonstrated={gaps.summary.preferred_demonstrated}
                partial={gaps.summary.preferred_partial}
                total={gaps.summary.preferred_total}
              />
            </div>
            {missingRequired.length > 0 && (
              <p>
                <strong>Required skills not yet shown in this repository:</strong>{" "}
                {missingRequired.map((r) => r.skill_label).join(", ")}
              </p>
            )}
            <p className="muted note">
              “Not demonstrated” means no evidence was found in the analyzed files of this repository. It does not
              mean the skill is absent.
            </p>
          </>
        )}
      </section>

      {gaps && (
        <section className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Requirement</th>
                <th>What the posting says</th>
                <th>In this repository</th>
              </tr>
            </thead>
            <tbody>
              {gaps.rows.map((r) => (
                <tr key={r.skill_key} className={r.status === "not_demonstrated" ? "gap-row" : ""}>
                  <td>
                    <strong>{r.skill_label}</strong>
                    <div>
                      <span className={`pill ${r.importance === "required" ? "req" : ""}`}>{r.importance}</span>
                    </div>
                  </td>
                  <td className="quote">“{r.quote}”</td>
                  <td>
                    <StatusBadge status={r.status} />
                    <div className="muted">{r.status === "demonstrated" && r.rationale ? r.rationale : r.message}</div>
                    <EvidenceList evidence={r.evidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
