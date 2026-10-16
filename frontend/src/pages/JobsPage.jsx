import { useEffect, useState } from "react";
import { api } from "../api.js";
import RequirementList from "../components/RequirementList.jsx";

export default function JobsPage({ onJobAdded }) {
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const refresh = () => api.listJobs().then(setJobs).catch((e) => setError(e.message));
  useEffect(() => {
    refresh();
  }, []);

  async function addJob(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const job = await api.createJob(url.trim(), showText ? text : null);
      setSelected(job);
      setUrl("");
      setText("");
      refresh();
      onJobAdded?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function openJob(id) {
    setError(null);
    try {
      setSelected(await api.getJob(id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeJob(id) {
    await api.deleteJob(id);
    if (selected?.id === id) setSelected(null);
    refresh();
  }

  return (
    <div className="jobs-layout">
      <section className="card">
        <h2>Add a job posting</h2>
        <form onSubmit={addJob} className="job-form">
          <input
            type="url"
            required
            placeholder="https://job-boards.greenhouse.io/company/jobs/123"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <label className="checkbox">
            <input type="checkbox" checked={showText} onChange={(e) => setShowText(e.target.checked)} />
            Not Greenhouse/Lever? Paste the posting text
          </label>
          {showText && (
            <textarea
              rows={8}
              placeholder="Paste the full job description here"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          )}
          <button disabled={busy}>{busy ? "Reading posting… (can take ~30s)" : "Extract requirements"}</button>
        </form>
        {error && <p className="error">{error}</p>}

        <h2>Saved jobs</h2>
        {jobs.length === 0 && <p className="muted">No jobs yet.</p>}
        <ul className="job-list">
          {jobs.map((j) => (
            <li key={j.id} className={selected?.id === j.id ? "active" : ""}>
              <button className="link" onClick={() => openJob(j.id)}>
                <strong>{j.company}</strong> — {j.title}
                <span className="muted"> ({j.requirement_count} skills)</span>
              </button>
              <button className="small" onClick={() => removeJob(j.id)} title="Delete">✕</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        {selected ? (
          <>
            <h2>
              {selected.company} — {selected.title}
            </h2>
            <p className="muted">
              {selected.location && <>{selected.location} · </>}
              Source:{" "}
              <a href={selected.source_url} target="_blank" rel="noreferrer">
                {selected.source_url}
              </a>{" "}
              ({selected.source_type})
            </p>
            {selected.dropped_requirements > 0 && (
              <p className="muted">
                {selected.dropped_requirements} extracted requirement(s) were discarded because their quote could
                not be found in the posting.
              </p>
            )}
            <RequirementList requirements={selected.requirements} />
          </>
        ) : (
          <p className="muted">Select or add a job to see its requirements.</p>
        )}
      </section>
    </div>
  );
}
