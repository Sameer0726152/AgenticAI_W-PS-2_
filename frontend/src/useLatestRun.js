import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const POLL_MS = 3000;

/** Checks the repo's latest run every few seconds; returns {run_id, status} and changes only when it changes. */
export function useLatestRun(repoId) {
  const [latest, setLatest] = useState({ run_id: null, status: null });
  const [error, setError] = useState(null);
  const current = useRef(latest);

  useEffect(() => {
    if (!repoId) return;
    current.current = { run_id: null, status: null };
    setLatest(current.current);
    let stopped = false;

    async function check() {
      try {
        const l = await api.latestRun(repoId);
        if (stopped) return;
        const c = current.current;
        if (l.run_id !== c.run_id || l.status !== c.status || l.last_polled_at !== c.last_polled_at || l.last_webhook_at !== c.last_webhook_at) {
          current.current = l;
          setLatest(l);
        }
        setError(null);
      } catch (e) {
        if (!stopped) setError(e.message);
      }
    }
    check();
    const timer = setInterval(check, POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [repoId]);

  return { latest, error };
}

export function formatTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
}
