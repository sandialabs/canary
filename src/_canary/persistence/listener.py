# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Results listener thread for asynchronous database writes.

The :class:`ResultListener` drains the workspace result spool
(``WorkspaceDatabase.queue``, an :class:`~_canary.util.fsqueue.FSQueue`) and writes records to the SQLite
database in batches.  It runs in a background thread, decoupling worker processes from
direct database access.

The spool is shared by every canary session running in the workspace, so a listener
may also persist records belonging to other sessions.  That is harmless because
:meth:`~_canary.persistence.database.WorkspaceDatabase.put_results` is order-independent
(an older record never replaces a newer one).  For the same reason the listener never
performs destructive recovery: claims and tmp files are only recovered once they are
much older than any live claim or write.
"""

import threading
import time
from pathlib import Path

from ..util import logging

logger = logging.get_logger(__name__)

#: Seconds after which an item left in ``claimed/`` is assumed to belong to a crashed
#: listener and is returned to ``ready/``.  A live claim is acked within milliseconds.
STALE_CLAIM_AGE = 900.0

#: Seconds after which a file left in ``tmp/`` is assumed to belong to a killed producer.
ORPHAN_TMP_AGE = 3600.0

#: Seconds between recovery sweeps.
MAINTENANCE_INTERVAL = 60.0


class ResultListener(threading.Thread):
    """Daemon thread that drains the shared result spool into the database.

    The listener creates its own database connection (SQLite connections are not
    shared across threads), polls the spool every ``poll_interval`` seconds, and
    performs a final drain when stopped so records written just before stop are not
    lost.
    """

    def __init__(self, db_root: Path, poll_interval: float = 0.05) -> None:
        super().__init__(daemon=True)
        from .database import WorkspaceDatabase

        self.db = WorkspaceDatabase.load(db_root)
        self.queue = self.db.queue
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._last_maintenance = float("-inf")

    def run(self) -> None:
        self.db.connect()
        try:
            while not self._stop_event.is_set():
                try:
                    self._maybe_recover()
                    self._drain_once()
                except Exception:
                    logger.exception("ResultListener drain failed")
                self._stop_event.wait(self.poll_interval)
            # Final drain so records written just before stop are not lost.
            try:
                self._maybe_recover()
                while self._drain_once():
                    pass
            except Exception:
                logger.exception("ResultListener final drain failed")
        finally:
            self.db.close()

    def _maybe_recover(self) -> None:
        now = time.monotonic()
        if now - self._last_maintenance < MAINTENANCE_INTERVAL:
            return
        self._last_maintenance = now
        self.queue.requeue_stale(older_than=STALE_CLAIM_AGE)
        self.queue.reap_tmp(older_than=ORPHAN_TMP_AGE)

    def _drain_once(self) -> bool:
        """Drain one batch.  Returns True if any records were processed."""
        batch = self.queue.receive()
        if not batch:
            return False
        paths, objs = zip(*batch)
        try:
            self.db.put_results(*objs)
        except Exception:
            # Return the records to ready/ so a later iteration (or listener) retries.
            self.queue.release(list(paths))
            raise
        self.queue.ack(list(paths))
        return True

    def stop_and_join(self) -> None:
        """Stop the listener and wait for the thread to finish."""
        self._stop_event.set()
        self.join()
