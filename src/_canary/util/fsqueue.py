# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""
FSQueue: a multi-producer, filesystem-backed queue for shared-FS HPC clusters.

Layout (all directories must live on the same filesystem so rename is atomic):

    root/
      tmp/      writers only; partial files live here
      ready/    committed items; the listener scans this (optionally sharded)
      claimed/  items owned by a listener until acked
      failed/   unparseable or repeatedly failing items, kept for inspection

Delivery is at-least-once: a listener crash after claim() but before ack()
leaves items in claimed/, and requeue_stale() returns them to ready/. Consumers
must therefore make DB inserts idempotent (unique event/job ID + upsert).

Ordering is by filename (time_ns~host~pid~seq): exact per producer, approximate
across nodes (subject to clock skew). Treat it as "roughly FIFO", not a total order.
"""

import heapq
import itertools
import os
import socket
import time
import zlib
from pathlib import Path
from typing import Any
from typing import Iterator

from . import json_helper as json

_SEP = "~"


class FSQueue:
    def __init__(
        self,
        root: Path | str,
        *,
        shards: int = 1,
        durable: bool = False,
        file_mode: int = 0o664,
        dir_mode: int = 0o775,
    ) -> None:
        """
        Args:
            root: queue root directory (created if needed).
            shards: number of hash-prefix subdirectories under ready/. Use >1 if
                ready/ can hold very large numbers of files. The consumer scans
                whatever exists, so changing this later is safe.
            durable: fsync each item before publishing it. Expensive on Lustre/GPFS;
                leave False if records can be reconstructed from job output.
            file_mode / dir_mode: creation modes (subject to umask), so a listener
                running as a different user/group can read and remove items.
        """
        self.root = Path(root)
        self.shards = max(1, int(shards))
        self.durable = durable
        self.file_mode = file_mode
        self.dir_mode = dir_mode

        self.tmp = self.root / "tmp"
        self.ready = self.root / "ready"
        self.claimed = self.root / "claimed"
        self.failed = self.root / "failed"

        for d in (self.tmp, self.ready, self.claimed, self.failed):
            self._mkdir(d)
        if self.shards > 1:
            for i in range(self.shards):
                self._mkdir(self.ready / f"{i:03d}")

        self._host = socket.gethostname().split(".")[0].replace(_SEP, "_").replace("/", "_")
        self._seq = itertools.count()

    # ------------------------------------------------------------------ helpers

    def _mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=self.dir_mode)

    def _ready_dir_for(self, name: str) -> Path:
        """Shard by producer (host+pid) so per-producer order is preserved."""
        if self.shards == 1:
            return self.ready
        producer = _SEP.join(name.split(_SEP)[1:3])
        return self.ready / f"{zlib.crc32(producer.encode()) % self.shards:03d}"

    def _scan_ready(self) -> Iterator[tuple[str, str]]:
        """Yield (name, path) for every item in ready/, including any shard subdirs."""
        subdirs: list[str] = []
        with os.scandir(self.ready) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    subdirs.append(e.path)
                else:
                    yield e.name, e.path
        for sd in subdirs:
            with os.scandir(sd) as it:
                for e in it:
                    yield e.name, e.path

    # ----------------------------------------------------------------- producer

    def put(self, obj: Any) -> None:
        """Serialize obj as JSON and atomically publish it to ready/."""
        payload = json.dumps(obj, separators=(",", ":")).encode()
        name = f"{time.time_ns():020d}{_SEP}{self._host}{_SEP}{os.getpid()}{_SEP}{next(self._seq)}"
        tmp_path = self.tmp / name
        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, self.file_mode)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                if self.durable:
                    f.flush()
                    os.fsync(f.fileno())
            os.rename(tmp_path, self._ready_dir_for(name) / name)  # single atomic publish
        except BaseException:  # includes KeyboardInterrupt / SystemExit from SIGTERM handlers
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    # ----------------------------------------------------------------- consumer

    def empty(self) -> bool:
        """Advisory only: True if ready/ has no items right now (NFS caching may lag)."""
        return next(self._scan_ready(), None) is None

    def claim(self, limit: int = 1000) -> list[Path]:
        """
        Atomically claim up to ``limit`` of the oldest ready items.

        Safe with multiple consumers: the rename loser gets ENOENT and skips the item.
        Returns paths in claimed/, oldest first.
        """
        oldest = heapq.nsmallest(limit, self._scan_ready(), key=lambda t: t[0])
        out: list[Path] = []
        for name, src in oldest:
            dst = self.claimed / name
            try:
                # Stamp claim time *before* the rename (rename preserves mtime), so
                # requeue_stale() never sees a freshly claimed item as old.
                os.utime(src)
                os.rename(src, dst)
            except FileNotFoundError:
                continue  # another consumer won this one
            out.append(dst)
        return out

    @staticmethod
    def load(path: Path) -> Any:
        """Parse a claimed item. Raises ValueError on malformed content."""
        return json.loads(Path(path).read_bytes())

    def receive(self, limit: int = 1000) -> list[tuple[Path, Any]]:
        """
        Claim and parse up to ``limit`` items. Unparseable items are moved to failed/.

        Returns (path, obj) pairs; pass the paths to ack() after the DB commit.
        """
        while True:
            claimed = self.claim(limit)
            if not claimed:
                return []
            batch: list[tuple[Path, Any]] = []
            for path in claimed:
                try:
                    batch.append((path, self.load(path)))
                except FileNotFoundError:
                    continue  # requeued out from under us
                except ValueError as e:  # JSONDecodeError / UnicodeDecodeError
                    self.fail(path, reason=repr(e))
            if batch:
                return batch

    @staticmethod
    def ack(paths: list[Path] | Path) -> None:
        """Delete processed items. Call only AFTER the DB transaction commits."""
        if isinstance(paths, (str, Path)):
            paths = [Path(paths)]
        for p in paths:
            Path(p).unlink(missing_ok=True)

    def fail(self, path: Path, reason: str | None = None) -> None:
        """Move a claimed item to failed/ (optionally with a .reason sidecar)."""
        path = Path(path)
        dst = self.failed / path.name
        try:
            os.rename(path, dst)
        except FileNotFoundError:
            return
        if reason:
            try:
                (self.failed / f"{path.name}.reason").write_text(reason)
            except OSError:
                pass

    def release(self, paths: list[Path] | Path) -> None:
        """Return claimed items to ready/ (e.g. transient DB error). Retried later."""
        if isinstance(paths, (str, Path)):
            paths = [Path(paths)]
        for p in paths:
            p = Path(p)
            try:
                os.rename(p, self._ready_dir_for(p.name) / p.name)
            except FileNotFoundError:
                pass

    # -------------------------------------------------------------- maintenance

    def requeue_stale(self, older_than: float = 900.0) -> int:
        """
        Return items claimed more than ``older_than`` seconds ago to ready/.

        Recovers from listener crashes. With a single listener, you can instead call
        this with older_than=0 once at startup. Compares local time.time() against file
        mtimes, so keep ``older_than`` much larger than any clock skew.
        """
        cutoff = time.time() - older_than
        n = 0
        with os.scandir(self.claimed) as it:
            for e in it:
                try:
                    if e.stat().st_mtime >= cutoff:
                        continue
                    os.rename(e.path, self._ready_dir_for(e.name) / e.name)
                    n += 1
                except FileNotFoundError:
                    continue  # acked or requeued concurrently
        return n

    def reap_tmp(self, older_than: float = 3600.0) -> int:
        """Delete orphaned tmp/ files left by killed producers. Returns count removed."""
        cutoff = time.time() - older_than
        n = 0
        with os.scandir(self.tmp) as it:
            for e in it:
                try:
                    if e.stat().st_mtime < cutoff:
                        os.unlink(e.path)
                        n += 1
                except FileNotFoundError:
                    continue
        return n
