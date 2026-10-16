function lineLabel(e) {
  if (!e.start_line) return "";
  return e.end_line && e.end_line !== e.start_line ? ` L${e.start_line}–${e.end_line}` : ` L${e.start_line}`;
}

export default function EvidenceList({ evidence }) {
  if (evidence.length === 0) return null;
  return (
    <ul className="evidence">
      {evidence.map((e, i) => (
        <li key={i}>
          <details>
            <summary>
              <a className="mono" href={e.permalink} target="_blank" rel="noreferrer">
                {e.path}
                {lineLabel(e)}
              </a>{" "}
              <span className="muted">({e.source})</span>
            </summary>
            {e.snippet && <pre className="snippet">{e.snippet}</pre>}
          </details>
        </li>
      ))}
    </ul>
  );
}
