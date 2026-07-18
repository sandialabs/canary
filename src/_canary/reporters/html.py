# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import html
import os
from argparse import Namespace
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
            "_create", nargs="?", choices=("create",), metavar="", help=argparse.SUPPRESS
        )
        parser.add_argument(
            "-o", "--output-dir", default="HTML", help="Output directory [default: %(default)s]"
        )
        parser.set_defaults(_html_report_handler=self.run_create)

    def run_from_args(self, args: Namespace) -> int:
        handler = getattr(args, "_html_report_handler", None)
        if handler is None:
            raise ValueError("canary report html: missing action")
        handler(args)
        return 0

    def run_create(self, args: Namespace) -> None:
        from ..workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        output_dir = Path(args.output_dir).absolute()
        request = HTMLReportRequest(workspace=workspace, jobs=jobs, output_dir=output_dir)
        HTMLReporter().write(request)


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

        save_manifest(final_dir, records)
        self.write_index_files(records, html_dir=final_dir)

        entrypoint = final_dir / "index.html"
        return entrypoint

    def write_index_files(self, records: dict[str, HTMLReportRecord], *, html_dir: Path) -> None:
        all_records = list(records.values())

        totals: dict[str, list[HTMLReportRecord]] = {}
        for record in all_records:
            totals.setdefault(record.group, []).append(record)

        for group in self.group_order:
            file = html_dir / f"{''.join(group.split())}.html"
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
        return """\
<style>
:root {
  --bg: #0f172a;
  --panel: #111827;
  --panel-2: #1f2937;
  --text: #e5e7eb;
  --muted: #9ca3af;
  --border: #374151;
  --link: #60a5fa;

  --pass: #22c55e;
  --fail: #ef4444;
  --diff: #f97316;
  --timeout: #eab308;
  --skip: #a78bfa;
  --cancel: #ec4899;
  --invalid: #f43f5e;
  --none: #94a3b8;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background:
    radial-gradient(circle at top left, rgba(96,165,250,0.18), transparent 30rem),
    radial-gradient(circle at top right, rgba(34,197,94,0.10), transparent 28rem),
    var(--bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
               "Segoe UI", sans-serif;
  line-height: 1.5;
}

main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

a {
  color: var(--link);
  text-decoration: none;
}

a:hover { text-decoration: underline; }

.header { margin-bottom: 2rem; }

.eyebrow {
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.75rem;
  font-weight: 700;
}

h1 {
  margin: 0.25rem 0 0.5rem;
  font-size: 2.4rem;
  line-height: 1.1;
}

h2 { margin-top: 0; }

.subtitle { color: var(--muted); }

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin: 1.5rem 0 2rem;
}

.card {
  display: block;
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.025));
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1rem;
  box-shadow: 0 10px 24px rgba(0,0,0,0.22);
  transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}

.card:hover {
  text-decoration: none;
  border-color: rgba(96,165,250,0.65);
  transform: translateY(-1px);
}

.card-label {
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.card-value {
  display: block;
  margin-top: 0.35rem;
  font-size: 2rem;
  font-weight: 800;
}

.panel {
  background: rgba(17,24,39,0.82);
  border: 1px solid var(--border);
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 14px 30px rgba(0,0,0,0.25);
}

.panel + .panel { margin-top: 1.5rem; }

.panel-header {
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.035);
}

.panel-title {
  margin: 0;
  font-size: 1rem;
  color: var(--text);
}

details.panel { margin-top: 1.5rem; }

details.panel:first-of-type { margin-top: 0; }

details.panel > summary {
  cursor: pointer;
  list-style: none;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.035);
  font-weight: 800;
}

details.panel > summary::-webkit-details-marker { display: none; }

details.panel > summary::before {
  content: "▾";
  display: inline-block;
  margin-right: 0.55rem;
  color: var(--muted);
  transition: transform 120ms ease;
}

details.panel:not([open]) > summary { border-bottom: none; }

details.panel:not([open]) > summary::before { transform: rotate(-90deg); }

table {
  width: 100%;
  border-collapse: collapse;
}

th {
  color: var(--muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  text-align: left;
  background: rgba(255,255,255,0.025);
}

td, th {
  padding: 0.8rem 1rem;
  border-bottom: 1px solid rgba(55,65,81,0.75);
  vertical-align: top;
}

tbody tr:last-child td { border-bottom: none; }

tr:hover td { background: rgba(96,165,250,0.06); }

.mono, .code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.muted { color: var(--muted); }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.03em;
  color: #020617;
  white-space: nowrap;
}

.badge-pass { background: var(--pass); }
.badge-fail { background: var(--fail); color: white; }
.badge-diff { background: var(--diff); color: white; }
.badge-timeout { background: var(--timeout); }
.badge-skip { background: var(--skip); color: white; }
.badge-cancel { background: var(--cancel); color: white; }
.badge-invalid { background: var(--invalid); color: white; }
.badge-none { background: var(--none); }

pre {
  margin: 0;
  padding: 1.25rem;
  overflow-x: auto;
  color: #d1d5db;
  background: #020617;
  border-radius: 14px;
  border: 1px solid var(--border);
}

.output { margin-top: 1.5rem; }

.meta-grid {
  display: grid;
  grid-template-columns: minmax(180px, 260px) 1fr;
}

.meta-grid > div {
  padding: 0.8rem 1rem;
  border-bottom: 1px solid rgba(55,65,81,0.75);
}

.meta-grid > div:nth-last-child(-n + 2) { border-bottom: none; }

.meta-key {
  color: var(--muted);
  font-weight: 700;
}

.measurement-value { white-space: pre-wrap; }

.footer {
  margin-top: 2rem;
  color: var(--muted);
  font-size: 0.85rem;
}

@media (max-width: 720px) {
  main { padding: 1rem; }
  h1 { font-size: 1.9rem; }
  .meta-grid { grid-template-columns: 1fr; }
  .meta-grid > div:nth-last-child(-n + 2) {
    border-bottom: 1px solid rgba(55,65,81,0.75);
  }
}
</style>
"""

    @property
    def head(self) -> str:
        return f'<head>\n<meta charset="utf-8">\n{self.style}\n</head>\n'

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

    def generate_case_file(self, job: "Job", fh: TextIO) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")

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

    def write_measurement_row(self, fh: TextIO, key: str, value: object) -> None:
        fh.write(f'<div class="meta-key">{html.escape(key)}</div>\n')
        fh.write(
            f'<div class="measurement-value">{html.escape(self.format_measurement(value))}</div>\n'
        )

    def format_measurement(self, value: object) -> str:
        if isinstance(value, float):
            return f"{value:.8g}"
        if isinstance(value, (int, bool, str)):
            return str(value)
        try:
            return json.dumps(value, indent=2)
        except Exception:
            return repr(value)

    def generate_index_records(
        self,
        records: list[HTMLReportRecord],
        *,
        totals: dict[str, list[HTMLReportRecord]],
        html_dir: Path,
        index: Path,
        fh: TextIO,
    ) -> None:
        group_files: dict[str, Path] = {}
        for group in self.group_order:
            if totals.get(group):
                group_files[group] = html_dir / f"{''.join(group.split())}.html"

        total_file = html_dir / "Total.html"

        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body><main>\n")

        fh.write('<section class="header">\n')
        fh.write('<div class="eyebrow">Canary Test Framework</div>\n')
        fh.write("<h1>Canary Report</h1>\n")
        fh.write(
            f'<div class="subtitle">Project '
            f"<b>{html.escape(str(config.get('cmake:project') or ''))}</b> "
            f"on <b>{html.escape(os.uname().nodename)}</b></div>\n"
        )
        fh.write("</section>\n")

        fh.write('<section class="cards">\n')
        self.write_card(fh, "Total", len(records), self.href(index, total_file))
        for group in self.group_order:
            n = len(totals.get(group, []))
            href = self.href(index, group_files[group]) if group in group_files else "#"
            self.write_card(fh, group, n, href)
        fh.write("</section>\n")

        fh.write('<section class="panel">\n')
        fh.write('<div class="panel-header"><h2 class="panel-title">Summary</h2></div>\n')
        fh.write("<table>\n<thead><tr>")
        for col in ("Group", "Count", "Link"):
            fh.write(f"<th>{html.escape(col)}</th>")
        fh.write("</tr></thead>\n<tbody>\n")

        for group in self.group_order:
            n = len(totals.get(group, []))
            if group in group_files:
                link = f'<a href="{self.href(index, group_files[group])}">View tests</a>'
            else:
                link = '<span class="muted">No tests</span>'
            fh.write(
                "<tr>"
                f'<td><span class="badge {self.badge_class(group)}">{html.escape(group)}</span></td>'
                f"<td>{n}</td>"
                f"<td>{link}</td>"
                "</tr>\n"
            )

        fh.write("</tbody></table>\n</section>\n")
        fh.write('<div class="footer">Generated by Canary.</div>\n')
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
            "<thead><tr><th>Status</th><th>Test</th><th>ID</th><th>Duration</th></tr></thead>\n"
        )
        fh.write("<tbody>\n")

        for record in sorted(records, key=lambda r: r.duration, reverse=True):
            fh.write(
                "<tr>"
                f"<td>{self.status_badge_record(record)}</td>"
                f"<td>{self.record_link(from_file=file, html_dir=html_dir, record=record)}</td>"
                f'<td class="code">{html.escape(record.id[:7])}</td>'
                f"<td>{record.duration:.2f}s</td>"
                "</tr>\n"
            )

        fh.write("</tbody>\n</table>\n</section>\n")
        fh.write("</main></body>\n</html>\n")

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
            "<thead><tr><th>Status</th><th>Test</th><th>ID</th><th>Duration</th></tr></thead>\n"
        )
        fh.write("<tbody>\n")

        for group in self.group_order:
            for record in sorted(totals.get(group, []), key=lambda r: r.duration):
                fh.write(
                    "<tr>"
                    f"<td>{self.status_badge_record(record)}</td>"
                    f"<td>{self.record_link(from_file=file, html_dir=html_dir, record=record)}</td>"
                    f'<td class="code">{html.escape(record.id[:7])}</td>'
                    f"<td>{record.duration:.2f}s</td>"
                    "</tr>\n"
                )

        fh.write("</tbody>\n</table>\n</section>\n")
        fh.write("</main></body>\n</html>\n")

    def record_link(self, *, from_file: Path, html_dir: Path, record: HTMLReportRecord) -> str:
        href = self.href(from_file, html_dir / record.page)
        text = html.escape(record.display_name)
        return f'<a href="{href}">{text}</a>'

    def href(self, from_file: Path, to_file: Path) -> str:
        return html.escape(os.path.relpath(to_file, from_file.parent), quote=True)


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
