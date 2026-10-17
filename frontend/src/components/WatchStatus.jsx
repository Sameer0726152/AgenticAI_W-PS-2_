import { useState } from "react";
import { api } from "../api.js";
import { formatTime } from "../useLatestRun.js";

/** "Watching GitHub for new commits · last checked 03:31:05" + a "Check now" button. */
export default function WatchStatus({ repoId, latest }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  async function checkNow() {
    setBusy(true);
    setMessage(null);
    try {
      const r = await api.checkNow(repoId);
      if (r.deferred) setMessage("New commit found; it will be assessed after the current run finishes.");
      else setMessage(r.new_commit ? `New commit ${r.commit_sha.slice(0, 7)} found, re-assessing…` : "No new commits.");
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="watch">
      <span className={`dot ${latest.polling ? "live" : ""}`} />
      <span className="muted">
        {latest.polling ? "Watching GitHub for new commits" : "Polling is off"}
        {latest.last_polled_at && <> · last checked {formatTime(latest.last_polled_at)}</>}
        {latest.last_webhook_at && <> · webhook push received {formatTime(latest.last_webhook_at)}</>}
        {latest.status === "running" && <strong> · re-assessing…</strong>}
      </span>
      <button className="secondary" onClick={checkNow} disabled={busy}>
        {busy ? "Checking…" : "Check now"}
      </button>
      {message && <span className="muted">{message}</span>}
    </div>
  );
}
