import StatusBadge from "./StatusBadge.jsx";
import { formatTime } from "../useLatestRun.js";

/** "Commit abc1234 changed tests/test_api.py → Unit testing: Not demonstrated → Demonstrated" */
export default function ChangeBanner({ trigger, commitSha, commitMessage, changedFiles, changes, finishedAt }) {
  if (!changedFiles?.length && !changes?.length) return null;
  return (
    <div className="banner">
      <div>
        <strong>Latest change</strong> ({trigger}, {formatTime(finishedAt)}): commit{" "}
        <span className="mono">{commitSha?.slice(0, 7)}</span> “{commitMessage}”
      </div>
      {changedFiles?.length > 0 && (
        <div className="muted">
          Changed files:{" "}
          {changedFiles.map((f) => (
            <span key={f.path} className="mono chip">
              {f.status} {f.path}
            </span>
          ))}
        </div>
      )}
      {changes?.length > 0 ? (
        <ul className="changes">
          {changes.map((c) => (
            <li key={c.skill_key}>
              <strong>{c.skill_label}</strong>: <StatusBadge status={c.from_status} /> → <StatusBadge status={c.to_status} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="muted">Affected skills were re-checked; no status changed.</div>
      )}
    </div>
  );
}
