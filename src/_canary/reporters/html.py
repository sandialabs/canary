# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import functools
import html
import http.server
import os
from argparse import Namespace
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING
from typing import TextIO

from .. import config
from ..hookspec import hookimpl
from ..util import json_helper as json
from ..util import logging
from ..util.filesystem import mkdirp
from .reporter import CanaryReporter
from .reporter import enabled

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..job import Job
    from ..runtest import Runner
    from ..workspace import Workspace

logger = logging.get_logger(__name__)

MANIFEST = "manifest.json"
REPORTER_PACKAGE = "_canary.reporters"

TEXT_EXTENSIONS = {
    ".bash",
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".csh",
    ".csv",
    ".err",
    ".f",
    ".f90",
    ".h",
    ".hpp",
    ".ini",
    ".i",
    ".inp",
    ".json",
    ".log",
    ".md",
    ".out",
    ".py",
    ".pyt",
    ".sh",
    ".txt",
    ".vvt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclasses.dataclass
class HTMLReportRequest:
    workspace: "Workspace"
    jobs: list["Job"]
    output_dir: Path


@dataclasses.dataclass
class HTMLReportRecord:
    id: str
    name: str
    display_name: str
    status: str
    group: str
    code: int
    reason: str
    duration: float
    session: str | None
    workspace: str
    page: str

    @classmethod
    def from_job(cls, job: "Job", reporter: "HTMLReporter") -> "HTMLReportRecord":
        return cls(
            id=job.id,
            name=job.name,
            display_name=job.display_name(),
            status=job.status.outcome.name,
            group=reporter.report_group(job),
            code=job.status.code,
            reason=job.status.reason or "",
            duration=job.timekeeper.duration(),
            session=job.workspace.session,
            workspace=str(job.workspace.dir),
            page=f"jobs/{job.id}.html",
        )


@hookimpl
def canary_reporter() -> CanaryReporter:
    return HTMLReportCommand()


@hookimpl(trylast=True)
def canary_runtests_report(runner: "Runner") -> None:
    """Create or update an HTML report for completed jobs."""
    if not enabled("html"):
        return

    ws = runner.workspace
    reporter = HTMLReporter()
    html_request = HTMLReportRequest(
        workspace=ws, jobs=runner.jobs, output_dir=ws.reports_dir / "html"
    )
    entrypoint = reporter.write(html_request)
    link = link_summary(runner.workspace.root.parent / "Canary.html", entrypoint)
    rel = os.path.relpath(link, config.invocation_dir)
    logger.info(f"HTML report written to {rel}")


class HTMLReportCommand(CanaryReporter):
    type = "html"
    description = "HTML reporter"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "_subcmd", nargs="?", choices=("create", "serve"), metavar="", help=argparse.SUPPRESS
        )
        parser.add_argument(
            "--serve",
            action="store_true",
            default=False,
            help=(
                "Serve the generated HTML report from a local HTTP server. "
                "Prints the localhost URL and blocks until interrupted. "
                "Useful for remote development workflows where tools such as VS Code "
                "can forward the printed port."
            ),
        )
        parser.add_argument(
            "-o", "--output-dir", default=None, help="Output directory [default: HTML]"
        )
        parser.set_defaults(_html_report_handler=self.run_cli)

    def run_from_args(self, args: Namespace) -> int:
        handler = getattr(args, "_html_report_handler", None)
        if handler is None:
            raise ValueError("canary report html: missing action")
        handler(args)
        return 0

    def run_cli(self, args: Namespace) -> None:
        if args.serve or args._subcmd == "serve":
            self.run_server(args)
        else:
            self.run_create(args)

    def run_create(self, args: Namespace) -> None:
        from ..workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        output_dir = Path(args.output_dir or "HTML").absolute()
        request = HTMLReportRequest(workspace=workspace, jobs=jobs, output_dir=output_dir)
        HTMLReporter().write(request)

    def run_server(self, args: Namespace) -> None:
        from ..workspace import Workspace

        entrypoint: Path
        if output_dir := getattr(args, "output_dir", None):
            entrypoint = Path(output_dir).absolute()
        else:
            workspace = Workspace.load()
            entrypoint = workspace.reports_dir / "html"

        index = entrypoint / "index.html" if entrypoint.is_dir() else entrypoint

        if not index.exists():
            raise ValueError(
                "No HTML report found to serve. Expected an index.html at "
                f"{index}. Generate one first with 'canary report html' or run tests "
                "with HTML reporting enabled."
            )

        if not index.is_file():
            raise ValueError(f"Cannot serve HTML report: {index} exists but is not a file.")

        serve_html_report(index)


class HTMLReporter:
    type = "html"
    description = "HTML reporter"

    group_order = ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Invalid", "Cancelled")

    def write(self, request: HTMLReportRequest) -> Path:
        """Update an HTML report in place and return its entry point."""
        final_dir = request.output_dir
        jobs_dir = final_dir / "jobs"
        mkdirp(jobs_dir)

        records = load_manifest(final_dir)

        for job in request.jobs:
            record = HTMLReportRecord.from_job(job, self)
            records[job.id] = record

            page = final_dir / record.page
            mkdirp(page.parent)
            tmp = page.with_name(f".{page.name}.tmp-{os.getpid()}")
            try:
                with open(tmp, "w") as fh:
                    self.generate_case_file(job, fh)
                os.replace(tmp, page)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise

            self.generate_file_browser(job, final_dir)

        copy_static_assets(final_dir)
        save_manifest(final_dir, records)
        self.write_index_files(records, html_dir=final_dir)

        return final_dir / "index.html"

    def write_index_files(self, records: dict[str, HTMLReportRecord], *, html_dir: Path) -> None:
        all_records = list(records.values())

        totals: dict[str, list[HTMLReportRecord]] = {}
        for record in all_records:
            totals.setdefault(record.group, []).append(record)

        for group in self.group_order:
            file = self.group_file(html_dir, group)
            group_records = totals.get(group, [])
            if group_records:
                self.write_group_index_records(group_records, file=file, html_dir=html_dir)
            else:
                file.unlink(missing_ok=True)

        total_file = html_dir / "Total.html"
        self.write_all_tests_index_records(totals, file=total_file, html_dir=html_dir)

        index = html_dir / "index.html"
        tmp = index.with_name(f".{index.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                self.generate_index_records(
                    all_records, totals=totals, html_dir=html_dir, index=index, fh=fh
                )
            os.replace(tmp, index)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    @property
    def style(self) -> str:
        css = load_template_text("style.css")
        return f"<style>\n{css}\n</style>\n"

    @property
    def head(self) -> str:
        return f'<head>\n<meta charset="utf-8">\n{self.style}\n</head>\n'

    @property
    def sort_script(self) -> str:
        return """\
<script>
function getCellValue(row, index, type) {
  const cell = row.children[index];
  if (!cell) {
    return "";
  }

  const sortValue = cell.getAttribute("data-sort");
  const text = sortValue !== null ? sortValue : cell.innerText.trim();

  if (type === "number") {
    const value = parseFloat(text);
    return Number.isNaN(value) ? Number.NEGATIVE_INFINITY : value;
  }

  return text.toLowerCase();
}

function sortTable(table, columnIndex, type) {
  const tbody = table.tBodies[0];
  if (!tbody) {
    return;
  }

  const header = table.tHead.rows[0].children[columnIndex];
  const descending = header.classList.contains("sort-asc");

  for (const th of table.tHead.rows[0].children) {
    th.classList.remove("sort-asc", "sort-desc");
  }
  header.classList.add(descending ? "sort-desc" : "sort-asc");

  const rows = Array.from(tbody.rows);
  rows.sort((a, b) => {
    const av = getCellValue(a, columnIndex, type);
    const bv = getCellValue(b, columnIndex, type);

    if (av < bv) return descending ? 1 : -1;
    if (av > bv) return descending ? -1 : 1;
    return 0;
  });

  for (const row of rows) {
    tbody.appendChild(row);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  for (const th of document.querySelectorAll("th.sortable")) {
    th.addEventListener("click", () => {
      const table = th.closest("table");
      const columnIndex = Array.prototype.indexOf.call(th.parentNode.children, th);
      const type = th.getAttribute("data-sort-type") || "text";
      sortTable(table, columnIndex, type);
    });
  }
});
</script>
"""

    def report_group(self, job: "Job") -> str:
        outcome = job.status.outcome.name

        if outcome == "NONE":
            return "Not Run"
        if outcome in {"SUCCESS", "XFAIL", "XDIFF"}:
            return "Pass"
        if outcome == "TIMEOUT":
            return "Timeout"
        if outcome == "DIFFED":
            return "Diff"
        if outcome in {"FAILED", "ERROR", "BROKEN"}:
            return "Fail"
        if outcome == "INVALID":
            return "Invalid"
        if outcome in {"CANCELLED", "INTERRUPTED"}:
            return "Cancelled"
        if outcome in {"SKIPPED", "BLOCKED"}:
            return "Not Run"

        return outcome.title()

    def badge_class(self, group: str) -> str:
        return {
            "Pass": "badge-pass",
            "Fail": "badge-fail",
            "Diff": "badge-diff",
            "Timeout": "badge-timeout",
            "Not Run": "badge-skip",
            "Cancelled": "badge-cancel",
            "Invalid": "badge-invalid",
        }.get(group, "badge-none")  # nosec B105

    def group_sort_key(self, group: str) -> int:
        try:
            return self.group_order.index(group)
        except ValueError:
            return len(self.group_order)

    def group_file(self, html_dir: Path, group: str) -> Path:
        return html_dir / f"{''.join(group.split())}.html"

    def status_badge(self, job: "Job") -> str:
        group = self.report_group(job)
        label = html.escape(job.status.outcome.name)
        glyph = html.escape(job.status.glyph())
        if glyph:
            label = f"{glyph} {label}"
        return f'<span class="badge {self.badge_class(group)}">{label}</span>'

    def status_badge_record(self, record: HTMLReportRecord) -> str:
        return (
            f'<span class="badge {self.badge_class(record.group)}">'
            f"{html.escape(record.status)}</span>"
        )

    def status_badge_link(
        self, *, from_file: Path, html_dir: Path, record: HTMLReportRecord
    ) -> str:
        href = self.href(from_file, self.group_file(html_dir, record.group))
        badge = self.status_badge_record(record)
        return f'<a class="badge-link" href="{href}">{badge}</a>'

    def generate_case_file(self, job: "Job", fh: TextIO) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")

        fh.write(
            '<a class="back-button" href="../index.html" '
            'onclick="if (history.length > 1) { history.back(); return false; }">'
            "← Back</a>\n"
        )

        fh.write('<section class="header">\n')
        fh.write('<div class="eyebrow">Test Case</div>\n')
        fh.write(f"<h1>{html.escape(job.display_name())}</h1>\n")
        fh.write(f'<div class="subtitle">{self.status_badge(job)}</div>\n')
        fh.write("</section>\n")

        self.write_metadata_panel(job, fh)
        self.write_measurements_panel(job, fh)

        fh.write('<section class="output">\n')
        fh.write("<h2>Test output</h2>\n<pre>")
        try:
            fh.write(html.escape(job.read_output()))
        except Exception:
            logger.exception(f"Failed reading output for job {job.id}")
            fh.write("Failed to read test output.")
        fh.write("</pre>\n</section>\n")

        fh.write("</main></body>\n</html>\n")

    def write_metadata_panel(self, job: "Job", fh: TextIO) -> None:
        fh.write('<details class="panel" open>\n')
        fh.write("<summary>Metadata</summary>\n")
        fh.write('<div class="meta-grid">\n')

        self.write_meta_row(fh, "Test", job.display_name())
        self.write_meta_row(fh, "Status", job.status.display_name())
        self.write_meta_row(fh, "Outcome", job.status.outcome.name)
        self.write_meta_row(fh, "Exit code", str(job.status.code))
        self.write_meta_row(fh, "ID", job.id)
        self.write_meta_row(fh, "Location", str(job.workspace.dir))
        self.write_meta_html_row(
            fh,
            "Files",
            f'<a href="../files/{html.escape(job.id, quote=True)}/index.html">'
            "Browse job artifacts</a>",
        )
        self.write_meta_row(fh, "Duration", f"{job.timekeeper.duration():.4f}s")

        if job.status.reason:
            self.write_meta_row(fh, "Reason", job.status.reason)

        fh.write("</div>\n")
        fh.write("</details>\n")

    def write_measurements_panel(self, job: "Job", fh: TextIO) -> None:
        measurements = list(job.measurements.items())

        fh.write('<details class="panel">\n')
        fh.write("<summary>Measurements</summary>\n")

        if not measurements:
            fh.write('<div class="meta-grid">\n')
            self.write_meta_row(fh, "Measurements", "None recorded")
            fh.write("</div>\n")
            fh.write("</details>\n")
            return

        fh.write('<div class="meta-grid">\n')
        for key, value in sorted(measurements, key=lambda item: str(item[0])):
            self.write_measurement_row(fh, str(key), value)
        fh.write("</div>\n")
        fh.write("</details>\n")

    def write_meta_row(self, fh: TextIO, key: str, value: str) -> None:
        fh.write(f'<div class="meta-key">{html.escape(key)}</div>\n')
        fh.write(f"<div>{html.escape(value)}</div>\n")

    def write_meta_html_row(self, fh: TextIO, key: str, value_html: str) -> None:
        fh.write(f'<div class="meta-key">{html.escape(key)}</div>\n')
        fh.write(f"<div>{value_html}</div>\n")

    def write_measurement_row(self, fh: TextIO, key: str, value: object) -> None:
        fh.write(f'<div class="meta-key">{html.escape(key)}</div>\n')
        fh.write(
            f'<div class="measurement-value">{html.escape(self.format_measurement(value))}</div>\n'
        )

    def format_measurement(self, value: object) -> str:
        scalar = (int, bool, str, float)
        if isinstance(value, float):
            return f"{value:.8g}"
        if isinstance(value, (int, bool, str)):
            return str(value)
        if isinstance(value, dict) and all(isinstance(x, scalar) for x in value.values()):
            return ", ".join(f"{k}={self.format_measurement(v)}" for k, v in value.items())
        try:
            return json.dumps(value, indent=2)
        except Exception:
            return repr(value)

    def generate_file_browser(self, job: "Job", html_dir: Path) -> None:
        root = job.workspace.dir
        files_dir = html_dir / "files" / job.id
        text_dir = files_dir / "text"
        mkdirp(text_dir)

        entries: list[tuple[Path, Path, bool, int]] = []

        if root.exists():
            for path in self.report_file_entries(job):
                try:
                    relpath = path.relative_to(root)
                except ValueError:
                    continue

                is_text = path.is_file() and is_plain_text_file(path)

                try:
                    size = path.stat().st_size
                except OSError:
                    size = -1

                entries.append((path, relpath, is_text, size))

                if is_text:
                    out = text_dir / safe_report_filename(relpath)
                    self.write_text_file_view(
                        source=path, relpath=relpath, output=out, back="../index.html"
                    )

        index = files_dir / "index.html"
        tmp = index.with_name(f".{index.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                self.generate_file_browser_index(job, entries=entries, file=index, fh=fh)
            os.replace(tmp, index)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def report_file_entries(self, job: "Job") -> list[Path]:
        root = job.workspace.dir
        relpaths: set[Path] = set()

        relpaths.add(Path("testcase.lock"))
        if job.stdout:
            relpaths.add(Path(job.stdout))
        if job.stderr:
            relpaths.add(Path(job.stderr))

        for rel in job.get_artifacts():
            relpaths.add(Path(rel))

        out: list[Path] = []
        for relpath in sorted(relpaths, key=lambda p: p.as_posix()):
            path = artifact_path(root, relpath)
            if path is None:
                continue
            if path.is_file() or path.is_symlink():
                out.append(path)

        return out

    def generate_file_browser_index(
        self, job: "Job", *, entries: list[tuple[Path, Path, bool, int]], file: Path, fh: TextIO
    ) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")

        fh.write(
            '<a class="back-button" href="../../jobs/'
            f'{html.escape(job.id, quote=True)}.html">'
            "← Back</a>\n"
        )

        fh.write('<section class="header">\n')
        fh.write('<div class="eyebrow">Result Files</div>\n')
        fh.write(f"<h1>{html.escape(job.display_name())}</h1>\n")
        fh.write(f'<div class="subtitle mono">{html.escape(str(job.workspace.dir))}</div>\n')
        fh.write("</section>\n")

        fh.write('<section class="panel">\n')
        fh.write('<div class="panel-header"><h2 class="panel-title">Files</h2></div>\n')
        fh.write("<table>\n")
        fh.write(
            "<thead><tr>"
            '<th class="sortable" data-sort-type="text">File</th>'
            '<th class="sortable" data-sort-type="number">Size</th>'
            '<th class="sortable" data-sort-type="text">Type</th>'
            "</tr></thead>\n"
        )
        fh.write("<tbody>\n")

        for _, relpath, is_text, size in entries:
            label = html.escape(relpath.as_posix())
            if is_text:
                target = file.parent / "text" / safe_report_filename(relpath)
                href = self.href(file, target)
                name = f'<a href="{href}">{label}</a>'
                kind = "text"
            else:
                name = label
                kind = "binary/unknown"

            fh.write(
                "<tr>"
                f'<td class="mono">{name}</td>'
                f'<td data-sort="{size}">{size}</td>'
                f"<td>{html.escape(kind)}</td>"
                "</tr>\n"
            )

        fh.write("</tbody>\n</table>\n</section>\n")
        fh.write("</main>\n")
        fh.write(self.sort_script)
        fh.write("</body>\n</html>\n")

    def write_text_file_view(
        self, *, source: Path, relpath: Path, output: Path, back: str, max_bytes: int = 512_000
    ) -> None:
        mkdirp(output.parent)

        truncated = False
        try:
            data = source.read_bytes()
        except OSError as e:
            text = f"Could not read file: {e}"
        else:
            if len(data) > max_bytes:
                data = data[:max_bytes]
                truncated = True
            text = data.decode("utf-8", errors="replace")

        tmp = output.with_name(f".{output.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                fh.write("<!doctype html>\n<html>\n")
                fh.write(self.head)
                fh.write("<body><main>\n")
                fh.write(
                    f'<a class="back-button" href="{html.escape(back, quote=True)}">← Back</a>\n'
                )

                fh.write('<section class="header">\n')
                fh.write('<div class="eyebrow">Text File</div>\n')
                fh.write(f"<h1>{html.escape(relpath.as_posix())}</h1>\n")
                if truncated:
                    fh.write('<div class="subtitle">File truncated for display.</div>\n')
                fh.write("</section>\n")

                fh.write("<pre>")
                fh.write(html.escape(text))
                fh.write("</pre>\n")

                fh.write("</main></body>\n</html>\n")
            os.replace(tmp, output)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def generate_index_records(
        self,
        records: list[HTMLReportRecord],
        *,
        totals: dict[str, list[HTMLReportRecord]],
        html_dir: Path,
        index: Path,
        fh: TextIO,
    ) -> None:
        group_files = {
            group: self.group_file(html_dir, group)
            for group in self.group_order
            if totals.get(group)
        }
        total_file = html_dir / "Total.html"

        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")

        fh.write('<section class="splash-header">\n')
        fh.write('<img class="logo" src="assets/canary.svg" alt="Canary logo">\n')
        fh.write('<div class="eyebrow">Canary Test Framework</div>\n')
        fh.write("<h1>Canary Report</h1>\n")
        fh.write(
            f'<div class="subtitle">Project '
            f"<b>{html.escape(str(config.get('cmake:project') or ''))}</b> "
            f"on <b>{html.escape(os.uname().nodename)}</b></div>\n"
        )
        fh.write("</section>\n")

        fh.write('<section class="cards cards-compact">\n')
        self.write_card(fh, "Total", len(records), self.href(index, total_file))
        for group in self.group_order:
            n = len(totals.get(group, []))
            href = self.href(index, group_files[group]) if group in group_files else "#"
            self.write_card(fh, group, n, href)
        fh.write("</section>\n")

        fh.write('<div class="footer splash-footer">Generated by Canary.</div>\n')
        fh.write("</main></body>\n</html>\n")

    def write_card(self, fh: TextIO, label: str, value: int, href: str) -> None:
        if href == "#":
            fh.write('<div class="card">\n')
        else:
            fh.write(f'<a class="card" href="{href}">\n')
        fh.write(f'<span class="card-label">{html.escape(label)}</span>\n')
        fh.write(f'<span class="card-value">{value}</span>\n')
        fh.write("</div>\n" if href == "#" else "</a>\n")

    def write_group_index_records(
        self, records: list[HTMLReportRecord], *, file: Path, html_dir: Path
    ) -> None:
        tmp = file.with_name(f".{file.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                self.generate_group_index_records(records, file=file, html_dir=html_dir, fh=fh)
            os.replace(tmp, file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def generate_group_index_records(
        self, records: list[HTMLReportRecord], *, file: Path, html_dir: Path, fh: TextIO
    ) -> None:
        group = records[0].group

        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")
        fh.write('<section class="header">\n')
        fh.write(f'<div class="eyebrow">{len(records)} tests</div>\n')
        fh.write(f"<h1>{html.escape(group)} Summary</h1>\n")
        fh.write('<div class="subtitle"><a href="index.html">Back to summary</a></div>\n')
        fh.write("</section>\n")

        fh.write('<section class="panel">\n')
        fh.write('<div class="panel-header"><h2 class="panel-title">Tests</h2></div>\n')
        fh.write("<table>\n")
        fh.write(
            "<thead><tr>"
            "<th>Status</th>"
            '<th class="sortable" data-sort-type="text">Test</th>'
            '<th class="sortable" data-sort-type="text">ID</th>'
            '<th class="sortable" data-sort-type="number">Duration</th>'
            "</tr></thead>\n"
        )
        fh.write("<tbody>\n")

        for record in sorted(records, key=lambda r: r.duration, reverse=True):
            fh.write(
                "<tr>"
                f"<td>{self.status_badge_record(record)}</td>"
                f"<td>{self.record_link(from_file=file, html_dir=html_dir, record=record)}</td>"
                f'<td class="code">{html.escape(record.id[:7])}</td>'
                f'<td data-sort="{record.duration:.12g}">{record.duration:.2f}s</td>'
                "</tr>\n"
            )

        fh.write("</tbody>\n</table>\n</section>\n")
        fh.write("</main>\n")
        fh.write(self.sort_script)
        fh.write("</body>\n</html>\n")

    def write_all_tests_index_records(
        self, totals: dict[str, list[HTMLReportRecord]], *, file: Path, html_dir: Path
    ) -> None:
        tmp = file.with_name(f".{file.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                self.generate_all_tests_index_records(totals, file=file, html_dir=html_dir, fh=fh)
            os.replace(tmp, file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def generate_all_tests_index_records(
        self, totals: dict[str, list[HTMLReportRecord]], *, file: Path, html_dir: Path, fh: TextIO
    ) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")
        fh.write('<section class="header">\n')
        fh.write(f'<div class="eyebrow">{sum(len(v) for v in totals.values())} tests</div>\n')
        fh.write("<h1>Test Results</h1>\n")
        fh.write('<div class="subtitle"><a href="index.html">Back to summary</a></div>\n')
        fh.write("</section>\n")

        fh.write('<section class="panel">\n')
        fh.write('<div class="panel-header"><h2 class="panel-title">All Tests</h2></div>\n')
        fh.write("<table>\n")
        fh.write(
            "<thead><tr>"
            '<th class="sortable" data-sort-type="number">Status</th>'
            '<th class="sortable" data-sort-type="text">Test</th>'
            '<th class="sortable" data-sort-type="text">ID</th>'
            '<th class="sortable" data-sort-type="number">Duration</th>'
            "</tr></thead>\n"
        )
        fh.write("<tbody>\n")

        for group in self.group_order:
            for record in sorted(totals.get(group, []), key=lambda r: r.duration):
                fh.write(
                    "<tr>"
                    f'<td data-sort="{self.group_sort_key(record.group)}">'
                    f"{self.status_badge_link(from_file=file, html_dir=html_dir, record=record)}"
                    "</td>"
                    f"<td>{self.record_link(from_file=file, html_dir=html_dir, record=record)}</td>"
                    f'<td class="code">{html.escape(record.id[:7])}</td>'
                    f'<td data-sort="{record.duration:.12g}">{record.duration:.2f}s</td>'
                    "</tr>\n"
                )

        fh.write("</tbody>\n</table>\n</section>\n")
        fh.write("</main>\n")
        fh.write(self.sort_script)
        fh.write("</body>\n</html>\n")

    def record_link(self, *, from_file: Path, html_dir: Path, record: HTMLReportRecord) -> str:
        href = self.href(from_file, html_dir / record.page)
        text = html.escape(record.display_name)
        return f'<a href="{href}">{text}</a>'

    def href(self, from_file: Path, to_file: Path) -> str:
        return html.escape(os.path.relpath(to_file, from_file.parent), quote=True)


def load_template_text(name: str) -> str:
    return resources.files(REPORTER_PACKAGE).joinpath(f"templates/html/{name}").read_text()


def load_manifest(report_dir: Path) -> dict[str, HTMLReportRecord]:
    path = report_dir / MANIFEST
    if not path.exists():
        return {}

    data = json.loads(path.read_text())
    records: dict[str, HTMLReportRecord] = {}
    for job_id, row in data.items():
        records[job_id] = HTMLReportRecord(**row)
    return records


def save_manifest(report_dir: Path, records: dict[str, HTMLReportRecord]) -> None:
    path = report_dir / MANIFEST
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")

    data = {job_id: dataclasses.asdict(record) for job_id, record in records.items()}
    try:
        with open(tmp, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def link_summary(summary: Path, entrypoint: Path) -> Path:
    """Create or replace a workspace-level Canary.html symlink."""
    target = os.path.relpath(entrypoint, summary.parent)
    if summary.is_symlink() or summary.is_file():
        summary.unlink()
    elif summary.exists():
        raise ValueError(f"{summary}: exists and is not a file or symlink")
    summary.symlink_to(target)
    return summary


def serve_html_report(entrypoint: Path | str, *, host: str = "127.0.0.1", port: int = 0) -> None:
    """
    Serve an HTML report directory on localhost.

    Args:
        entrypoint: Path to ``index.html`` or to the report directory containing ``index.html``.
        host: Interface to bind. Defaults to localhost only.
        port: Port to bind. Use 0 to request an available ephemeral port.

    This function prints only the URL, then blocks until interrupted.
    """
    path = Path(entrypoint).resolve()

    if path.is_dir():
        directory = path
        index = directory / "index.html"
    else:
        index = path
        directory = path.parent

    if not index.exists():
        raise FileNotFoundError(index)
    if not index.is_file():
        raise ValueError(f"{index}: not a file")

    class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

    handler = functools.partial(QuietHTTPRequestHandler, directory=str(directory))

    with http.server.ThreadingHTTPServer((host, port), handler) as server:
        bound_host, bound_port = server.server_address[:2]
        url = f"http://{bound_host}:{bound_port}/index.html"
        print(f"HTML report served at {url}", flush=True)

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def copy_static_assets(output_dir: Path) -> None:
    assets_dir = output_dir / "assets"
    mkdirp(assets_dir)

    for name in ("canary.svg",):
        src = resources.files(REPORTER_PACKAGE).joinpath(f"templates/html/{name}")
        if src.is_file():
            (assets_dir / name).write_bytes(src.read_bytes())


def is_plain_text_file(path: Path, *, max_probe_bytes: int = 8192) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    try:
        data = path.read_bytes()[:max_probe_bytes]
    except OSError:
        return False

    if b"\x00" in data:
        return False

    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def safe_report_filename(relpath: Path) -> str:
    parts = [p for p in relpath.parts if p not in ("", ".", "..")]
    return "__".join(parts) + ".html"


def artifact_path(workspace_dir: Path, relpath: Path) -> Path | None:
    """
    Join an artifact path to the workspace directory without resolving the
    final path. This preserves symlinks that point outside the workspace.

    Reject absolute paths and parent traversal.
    """
    if relpath.is_absolute():
        return None
    if any(part in ("", ".", "..") for part in relpath.parts):
        return None
    return workspace_dir / relpath
