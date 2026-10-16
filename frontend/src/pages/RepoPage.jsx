import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function RepoPage() {
  const [repos, setRepos] = useState([]);
  const [fullName, setFullName] = useState("");
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [showSkipped, setShowSkipped] = useState(false);

  const refresh = () => api.listRepos().then(setRepos).catch((e) => setError(e.message));
  useEffect(() => {
    refresh();
  }, []);

  async function connect(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.connectRepo(fullName.trim(), branch.trim());
      setFullName("");
      setBranch("");
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id) {
    await api.deleteRepo(id);
    refresh();
  }

  return (
    <div className="stack">
      <section className="card">
        <h2>Connect a GitHub repository</h2>
        <form onSubmit={connect} className="row-form">
          <input
            required
            placeholder="owner/repo or https://github.com/owner/repo"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          <input placeholder="branch (default)" value={branch} onChange={(e) => setBranch(e.target.value)} />
          <button disabled={busy}>{busy ? "Reading repository…" : "Connect"}</button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      {repos.length === 0 && <p className="muted">No repository connected yet.</p>}

      {repos.map((repo) => {
        const snap = repo.latest_snapshot;
        const files = snap ? snap.files.filter((f) => showSkipped || f.included) : [];
        return (
          <section className="card" key={repo.id}>
            <div className="card-head">
              <h2>
                <a href={repo.html_url} target="_blank" rel="noreferrer">
                  {repo.full_name}
                </a>{" "}
                <span className="pill">{repo.branch}</span>
              </h2>
              <button className="small" onClick={() => remove(repo.id)} title="Disconnect">
                ✕
              </button>
            </div>
            {snap && (
              <>
                <p>
                  Latest commit{" "}
                  <a className="mono" href={snap.commit_url} target="_blank" rel="noreferrer">
                    {snap.commit_sha.slice(0, 7)}
                  </a>{" "}
                  — {snap.commit_message} <span className="muted">({snap.committed_at})</span>
                </p>
                <p className="muted">
                  {snap.files_included} files selected for analysis · {snap.files_skipped} skipped{" "}
                  <label className="checkbox inline">
                    <input type="checkbox" checked={showSkipped} onChange={(e) => setShowSkipped(e.target.checked)} />
                    show skipped
                  </label>
                </p>
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>File</th>
                        <th>Size</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {files.map((f) => (
                        <tr key={f.path}>
                          <td className="mono">
                            <a href={f.url} target="_blank" rel="noreferrer">
                              {f.path}
                            </a>
                          </td>
                          <td className="muted">{f.size} B</td>
                          <td>
                            {f.included ? (
                              <span className="pill ok">analyzed</span>
                            ) : (
                              <span className="pill">skipped: {f.skip_reason}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
