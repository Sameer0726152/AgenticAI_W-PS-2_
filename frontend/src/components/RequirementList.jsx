export default function RequirementList({ requirements }) {
  if (requirements.length === 0) return <p className="muted">No technical requirements found.</p>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Skill</th>
          <th>Importance</th>
          <th>Quote from posting</th>
        </tr>
      </thead>
      <tbody>
        {requirements.map((r) => (
          <tr key={r.id}>
            <td>
              <strong>{r.skill_label}</strong>
              <div className="muted mono">{r.skill_key}</div>
            </td>
            <td>
              <span className={`pill ${r.importance === "required" ? "req" : ""}`}>{r.importance}</span>
            </td>
            <td className="quote">“{r.quote}”</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
