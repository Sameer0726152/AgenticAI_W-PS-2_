import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import EvidenceList from "../components/EvidenceList.jsx";
import StatusBadge from "../components/StatusBadge.jsx";

const POLL_MS = 3000;

export default function AssessmentPage() {
  const [repos, setRepos] = useState([]);
  const [repoId, setRepoId] = useState(null);
  const [run, setRun] = useState(null);
  const [error, setError] = useState(null);
  const latest = useRef({ run_id: null, status: null });

  useEffect(() => {
    api
      .listRepos()
      .then((rs) => {
        setRepos(rs);
        if (rs.length) setRepoId(rs[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  // Check for a new or finished run every few seconds; reload details only when something changed.
  useEffect(() => {
    if (!repoId) return;
    latest.current = { run_id: null, status: null };
    setRun(null);
    let stopped = false;

    async function check() {
      try {
        const l = await api.latestRun(repoId);
        if (stopped) return;
        if (l.run_id && (l.run_id !== latest.current.run_id || l.status !== latest.current.status)) {
          latest.current = l;
          setRun(await api.getRun(l.run_id));
        }
        setError(null);
      } catch (e) {
        setError(e.message);
      }
    }
    check();
    const timer = setInterval(check, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [repoId]);

  async function rerun() {
    setError(null);
    try {
      await api.assess(repoId);
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
        {error && <p className="error">{error}</p>}
        {!run && <p className="muted">No assessment yet. Click “Re-run assessment”.</p>}
        {run && (
          <p className="muted">
            Run #{run.id} · commit <span className="mono">{run.commit_sha.slice(0, 7)}</span> “{run.commit_message}” ·
            trigger: {run.trigger} · status: <strong>{run.status}</strong>
            {run.finished_at && <> · finished {run.finished_at}</>}
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
