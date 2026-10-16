const LABELS = {
  demonstrated: "Demonstrated",
  partially_demonstrated: "Partially demonstrated",
  not_demonstrated: "Not demonstrated",
};

export default function StatusBadge({ status }) {
  return <span className={`pill status-${status}`}>{LABELS[status] || status}</span>;
}
