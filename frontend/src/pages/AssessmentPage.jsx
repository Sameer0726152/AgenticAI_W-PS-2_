import { useEffect, useState } from "react";
import { api } from "../api.js";
import EvidenceList from "../components/EvidenceList.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { formatTime, useLatestRun } from "../useLatestRun.js";

export default function AssessmentPage() {
  const [repos, setRepos] = useState([]);
  const [repoId, setRepoId] = useState(null);
  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const [requested, setRequested] = useState(null); // run id started from this page
  const { latest, error: pollError } = useLatestRun(repoId);

  useEffect(() => {
    api
      .listRepos()
      .then((rs) => {
        setRepos(rs);
        if (rs.length) setRepoId(rs[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!latest.run_id) {
      setRun(null);
      return;
    }
    api.getRun(latest.run_id).then(setRun).catch((e) => setError(e.message));
  }, [latest.run_id, latest.status]);

  async function rerun() {
    setError(null);
    try {
      const r = await api.assess(repoId);
      setRequested(r.run_id);
    } catch (e) {
      setError(e.message);
    }
  }

  if (repos.length === 0) {
    return <p className="muted stack">Connect a repository in the Repository tab first.</p>;
  }

  const running = run?.status === "running";
  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <h2>Skill assessment</h2>
          <div className="row-form">
            <select value={repoId ?? ""} onChange={(e) => setRepoId(Number(e.target.value))}>
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name} ({r.branch})
                </option>
              ))}
            </select>
            <button onClick={rerun} disabled={running}>
              {running ? "Assessing…" : "Re-run assessment"}
            </button>
          </div>
        </div>
        {(error || pollError) && <p className="error">{error || pollError}</p>}
        {!run && <p className="muted">No assessment yet. Click “Re-run assessment”.</p>}
        {run && (
          <p className="muted">
            Run #{run.id} · commit <span className="mono">{run.commit_sha.slice(0, 7)}</span> “{run.commit_message}” ·
            trigger: {run.trigger} · status: <strong>{run.status}</strong>
            {run.finished_at && <> · finished {formatTime(run.finished_at)}</>}
          </p>
        )}
        {requested && run?.id === requested && run.status === "done" && (
          <p className="notice">
            Run #{run.id} finished at {formatTime(run.finished_at)}.
            {run.prev_run_id ? " Same commit as before, so results are unchanged (reused from cache, 0 tokens)." : ""}
          </p>
        )}
        {run?.status === "failed" && <p className="error">Assessment failed: {run.error}</p>}
        <p className="muted note">
          “Not demonstrated” means no evidence was found in the analyzed files of this repository. It does not mean
          the skill is absent.
        </p>
      </section>

      {run && run.skills.length > 0 && (
        <section className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Skill</th>
                <th>Status</th>
                <th>Why / evidence</th>
              </tr>
            </thead>
            <tbody>
              {run.skills.map((s) => (
                <tr key={s.skill_key}>
                  <td>
                    <strong>{s.skill_label}</strong>
                    <div className="muted mono">{s.skill_key}</div>
                  </td>
                  <td>
                    <StatusBadge status={s.status} />
                    {s.confidence && <div className="muted">confidence: {s.confidence}</div>}
                    <div className="muted">method: {s.method}</div>
                  </td>
                  <td>
                    <div>{s.rationale}</div>
                    <EvidenceList evidence={s.evidence} />
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
