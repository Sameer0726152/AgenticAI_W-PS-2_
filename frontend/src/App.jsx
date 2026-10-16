import { useEffect, useState } from "react";
import { api } from "./api.js";
import JobsPage from "./pages/JobsPage.jsx";
import RepoPage from "./pages/RepoPage.jsx";

const TABS = [
  { id: "jobs", label: "Jobs" },
  { id: "repo", label: "Repository" },
];

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [tab, setTab] = useState("jobs");

  const refreshHealth = () =>
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((e) => setHealthError(e.message));

  useEffect(() => {
    refreshHealth();
  }, []);

  return (
    <div className="app">
      <header className="header">
        <h1>AI Career Coach</h1>
        <div className="health">
          {healthError && <span className="pill bad">Backend: offline</span>}
          {health && (
            <>
              <span className="pill ok">Backend: {health.status}</span>
              <span className={`pill ${health.llm_key_configured ? "ok" : "bad"}`}>
                LLM: {health.llm_provider}
              </span>
              <span className={`pill ${health.github_token_configured ? "ok" : "bad"}`}>GitHub token</span>
              <span className="pill">Tokens today: {health.tokens_used_today}</span>
            </>
          )}
        </div>
      </header>
      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "tab active" : "tab"} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      <main>
        {tab === "jobs" && <JobsPage onJobAdded={refreshHealth} />}
        {tab === "repo" && <RepoPage />}
      </main>
    </div>
  );
}
