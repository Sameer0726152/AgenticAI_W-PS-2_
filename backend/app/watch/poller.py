"""Background thread: checks every tracked repo for new commits and re-assesses affected skills."""
import logging
import threading

from app import config, db
from app.assessment.pipeline import execute_run, handle_new_commit

log = logging.getLogger(__name__)


class Poller:
    def __init__(self, interval: int):
        self.interval = interval
        self.last_tick: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="repo-poller", daemon=True)
        self._thread.start()
        log.info("Poller started (every %ss)", self.interval)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval)

    def tick(self) -> None:
        with db.transaction() as conn:
            repo_ids = [r["id"] for r in conn.execute("SELECT id FROM repos WHERE polling_enabled = 1")]
        for repo_id in repo_ids:
            try:
                result = handle_new_commit(repo_id, "poll")
                if result["new_commit"] and result["run_id"]:
                    execute_run(result["run_id"])
            except Exception:
                log.exception("Polling repo %s failed", repo_id)
        self.last_tick = db.utc_now()


poller = Poller(config.POLL_INTERVAL_SECONDS)
