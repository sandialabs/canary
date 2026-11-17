# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Results listener thread for asynchronous database writes.

The :class:`ResultListener` drains a filesystem-based result spool and writes
records to the SQLite database in batches. It runs in a background thread,
decoupling worker processes from direct database access.

Worker processes write results to an :class:`~_canary.util.fsqueue.FSQueue` spool,
and the listener drains the spool to persist results. This ensures only a
single thread writes to SQLite, avoiding lock contention from multiple processes.
"""

import threading
import time
from typing import TYPE_CHECKING

from ..util import logging

if TYPE_CHECKING:
    pass

logger = logging.get_logger(__name__)


class ResultListener(threading.Thread):
    """Daemon thread that drains the result spool and writes to the database.

    Watches the workspace-wide result spool (filesystem-based queue) and writes
    results to SQLite in batches. Runs as a daemon thread so it doesn't block
    process exit.

    The listener creates its own database connection to avoid sharing connections
    across threads. It polls the spool at regular intervals and performs a final
    drain when stopped to ensure no results are lost.

    Attributes:
        db: WorkspaceDatabase instance (with its own connection).
        queue: FSQueue instance to drain.
        poll_interval: Seconds between drain attempts.
    """

    def __init__(self, db_root, poll_interval: float = 0.05) -> None:
        """Initialize the listener.

        Args:
            db_root: Path to workspace root (used to create database connection).
            poll_interval: Seconds to sleep between drain attempts.
        """
        super().__init__(daemon=True)
        # Import here to avoid circular dependency
        from .database import WorkspaceDatabase

        self.db = WorkspaceDatabase.load(db_root)
        self.queue = self.db.queue._queue
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._processed: set[str] = set()

    def run(self):
        """Main thread loop."""
        self.db.connect()
        try:
            # Recover any records left claimed by a previous crashed listener
            self.queue.reap_tmp(older_than=0)
            self.queue.requeue_stale(older_than=0)

            while not self._stop_event.is_set():
                try:
                    self._drain_once()
                except Exception:
                    logger.exception("ResultListener drain failed")
                time.sleep(self.poll_interval)

            # Final drain so records written just before stop are not lost
            while True:
                try:
                    if not self._drain_once():
                        break
                except Exception:
                    logger.exception("ResultListener final drain failed")
                    break
        finally:
            self.db.close()

    def _drain_once(self) -> bool:
        """Drain the queue once. Returns True if data was processed."""
        batch = self.queue.receive()
        if not batch:
            return False

        paths, objs = zip(*batch)

        try:
            self.db.put_results(*objs)
        except Exception:
            # Do not lose records if SQLite write fails. Return them to ready/
            # so a later listener iteration/process can retry.
            self.queue.release(list(paths))
            raise

        self.queue.ack(list(paths))
        self._processed.update(obj.id for obj in objs)
        return True

    def stop_and_join(self):
        """Stop the listener and wait for the thread to finish."""
        self._stop_event.set()
        self.join()
