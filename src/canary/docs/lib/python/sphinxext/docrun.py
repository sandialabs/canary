# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Simplified Sphinx ``doc-run`` directive.

Directive model
---------------

``doc-run`` executes commands during a Sphinx build and renders only the output
from the main ``script`` phase.

Each directive has three phases:

- ``before_script``: setup commands, hidden output, stop on first failure
- ``script``: main commands, rendered output, stop on first failure
- ``after_script``: teardown commands, hidden output, always run all commands

Commands are specified as strict inline JSON arrays of command objects.

Example::

    .. doc-run::
       :before_script: [{"args": "mkdir work"}, {"args": "cp ${doc_source_dir}/foo.pyt work/"}]
       :script: [{"args": "canary run foo.pyt", "cwd": "work", "ellipsis": 20}]
       :after_script: [{"args": "rm -rf work"}]

Command schema
--------------

Each command object has:

- ``args``: required string passed to ``subprocess.run(..., shell=True)``
- ``cwd``: optional working directory relative to the temporary run directory
- ``returns``: optional expected return code, default ``0``
- ``ellipsis``: optional non-negative integer; for rendered script output only

Caching
-------

A single generational cache is stored at::

    <sphinx-source-dir>/dccache.json

The cache is split by the set of documents Sphinx is processing in the current
build.

- Entries for documents not processed in this build are preserved.
- Entries for documents processed in this build are placed in a temporary cache.
- Cache hits from that temporary cache are transferred into the new cache.
- Cache misses are executed and stored in the new cache.
- At build finish, preserved entries and new entries are merged and written.

This prevents unbounded cache growth while still preserving cache entries for
documents skipped by local incremental Sphinx builds.

Template variables
------------------

Command ``args`` strings support Python ``string.Template`` expansion with:

- ``${doc_source_dir}``: directory containing the current RST source file
- ``${doc_name}``: Sphinx document name
- ``${examples}``: Canary's installed ``docs/examples`` directory, if available

Cache keys use the raw, unexpanded directive command specs so they remain stable
across machines, checkout directories, and virtual environments.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from string import Template
from typing import Any
from typing import Iterable

from docutils import nodes
from docutils.parsers import rst
from sphinx.util import logging as sphinx_logging

__version__ = "1.0"

CACHE_SCHEMA = 2
EXECUTION_MODEL = "temp-shell-json-v2"
CACHE_FILENAME = "dccache.json"

logger = sphinx_logging.getLogger("sphinxext.docrun")


class doc_run_output(nodes.Element):
    """Placeholder node replaced by cached or freshly executed command output."""


@dataclasses.dataclass(frozen=True, slots=True)
class CommandSpec:
    """One shell command in a doc-run phase."""

    args: str
    cwd: str | None = None
    returns: int = 0
    ellipsis: int | None = None

    @classmethod
    def from_json_obj(cls, obj: Any, *, index: int) -> "CommandSpec":
        """Validate and normalize one JSON command object."""
        if not isinstance(obj, dict):
            raise ValueError(f"command {index} must be a JSON object")

        allowed = {"args", "cwd", "returns", "ellipsis"}
        unknown = sorted(set(obj) - allowed)
        if unknown:
            raise ValueError(
                f"command {index} has unknown key(s): {', '.join(unknown)}; "
                f"allowed keys are: {', '.join(sorted(allowed))}"
            )

        if "args" not in obj:
            raise ValueError(f"command {index} requires key 'args'")

        args = obj["args"]
        if not isinstance(args, str) or not args.strip():
            raise ValueError(f"command {index} field 'args' must be a non-empty string")

        cwd = obj.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise ValueError(f"command {index} field 'cwd' must be a string if provided")

        returns = obj.get("returns", 0)
        if isinstance(returns, bool) or not isinstance(returns, int) or returns < 0:
            raise ValueError(
                f"command {index} field 'returns' must be a non-negative integer if provided"
            )

        ellipsis = obj.get("ellipsis")
        if ellipsis is not None:
            if isinstance(ellipsis, bool) or not isinstance(ellipsis, int) or ellipsis < 0:
                raise ValueError(
                    f"command {index} field 'ellipsis' must be a non-negative integer if provided"
                )

        return cls(args=args, cwd=cwd, returns=returns, ellipsis=ellipsis)

    def to_json_obj(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        data: dict[str, Any] = {"args": self.args, "cwd": self.cwd, "returns": self.returns}
        if self.ellipsis is not None:
            data["ellipsis"] = self.ellipsis
        return data


@dataclasses.dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured result from one executed command."""

    spec: CommandSpec
    output: str
    returncode: int | None
    error: str | None = None

    @property
    def failed(self) -> bool:
        """Return True if the command failed relative to its expected return code."""
        if self.returncode is None:
            return True
        return self.returncode != self.spec.returns


@dataclasses.dataclass(frozen=True, slots=True)
class RunResult:
    """Complete result from before_script, script, and after_script."""

    before_script: list[CommandResult]
    script: list[CommandResult]
    after_script: list[CommandResult]

    @property
    def failed(self) -> bool:
        """Return True if any phase failed."""
        return any(result.failed for result in self.before_script + self.script + self.after_script)


class DocRunCache:
    """Incremental-safe generational source-tree cache for doc-run transcripts."""

    def __init__(self, path: Path, original_entries: dict[str, Any]) -> None:
        self.path = path
        self.original_entries = original_entries

        self.persistent_entries: dict[str, Any] = {}
        self.tmp_entries: dict[str, Any] = {}
        self.new_entries: dict[str, Any] = {}

        self.docnames_to_process: set[str] = set()
        self.split_done = False

    def split_for_docs(self, *, docnames_to_process: set[str], found_docs: set[str]) -> None:
        """Split original cache according to documents processed by this build.

        Entries for processed documents go to ``tmp_entries``.  Entries for
        unprocessed documents go to ``persistent_entries``.  Entries for deleted
        documents or incompatible entries are dropped.
        """
        self.docnames_to_process = set(docnames_to_process)
        self.persistent_entries = {}
        self.tmp_entries = {}
        self.new_entries = {}

        dropped = 0
        for key, entry in self.original_entries.items():
            if not self._usable_entry(key, entry):
                dropped += 1
                continue

            docname = entry["docname"]
            if docname not in found_docs:
                dropped += 1
                continue

            if docname in self.docnames_to_process:
                self.tmp_entries[key] = entry
            else:
                self.persistent_entries[key] = entry

        self.split_done = True

        logger.info(
            "[doc-run] cache split: process=%d persistent=%d tmp=%d dropped=%d",
            len(self.docnames_to_process),
            len(self.persistent_entries),
            len(self.tmp_entries),
            dropped,
        )

    def ensure_split(self, *, found_docs: set[str]) -> None:
        """Ensure cache has been split.

        This is a fallback for unusual Sphinx execution paths where
        ``env-before-read-docs`` did not run before ``doctree-read``.
        """
        if not self.split_done:
            logger.warning(
                "[doc-run] cache was not split before doctree-read; treating build as full read"
            )
            self.split_for_docs(docnames_to_process=set(found_docs), found_docs=set(found_docs))

    def get(self, key: str) -> str | None:
        """Return cached transcript for ``key``, transferring hit into new cache."""
        entry = self.tmp_entries.get(key)
        if not self._usable_entry(key, entry):
            return None

        transcript = entry["transcript"]

        self.new_entries[key] = entry
        self.tmp_entries.pop(key, None)
        return transcript

    def put(self, key: str, *, docname: str, transcript: str) -> None:
        """Store a successful transcript in the new cache."""
        self.new_entries[key] = {
            "schema": CACHE_SCHEMA,
            "execution_model": EXECUTION_MODEL,
            "docname": docname,
            "transcript": transcript,
        }

    def write(self) -> None:
        """Write preserved plus newly used/generated entries to disk."""
        final_entries: dict[str, Any] = {}
        final_entries.update(self.persistent_entries)
        final_entries.update(self.new_entries)

        payload = {
            "schema": CACHE_SCHEMA,
            "execution_model": EXECUTION_MODEL,
            "entries": final_entries,
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")

        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")

        os.replace(tmp, self.path)

        logger.info(
            "[doc-run] wrote cache: persistent=%d new=%d total=%d path=%s",
            len(self.persistent_entries),
            len(self.new_entries),
            len(final_entries),
            self.path,
        )

    @staticmethod
    def _usable_entry(key: str, entry: Any) -> bool:
        """Return True if a cache entry has the expected shape."""
        if not isinstance(key, str):
            return False
        if not isinstance(entry, dict):
            return False
        if entry.get("schema") != CACHE_SCHEMA:
            return False
        if entry.get("execution_model") != EXECUTION_MODEL:
            return False
        if not isinstance(entry.get("docname"), str):
            return False
        if not isinstance(entry.get("transcript"), str):
            return False
        return True


def _commands_json(value: str) -> list[CommandSpec]:
    """Parse a strict inline JSON array of command objects."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"script option must be strict JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("script option must be a JSON array of command objects")

    return [CommandSpec.from_json_obj(item, index=i) for i, item in enumerate(parsed)]


def _command_specs_from_node(node: doc_run_output, name: str) -> list[CommandSpec]:
    """Reconstruct command specs from node attributes."""
    return [CommandSpec.from_json_obj(item, index=i) for i, item in enumerate(node.get(name) or [])]


def _resolve_cwd(temp_root: Path, cwd: str | None) -> Path:
    """Resolve command cwd relative to the temporary run directory."""
    if cwd is None or cwd.strip() in {"", "."}:
        return temp_root

    raw = cwd.strip().replace("\\", "/")
    path = Path(raw)

    if path.is_absolute():
        raise ValueError(f"cwd must be relative to the temporary run directory: {cwd!r}")

    if any(part == ".." for part in path.parts):
        raise ValueError(f"cwd escapes temporary run directory: {cwd!r}")

    resolved = temp_root / path

    if not resolved.is_dir():
        raise FileNotFoundError(f"cwd does not exist inside temporary run directory: {cwd!r}")

    return resolved


def _run_one(spec: CommandSpec, *, temp_root: Path) -> CommandResult:
    """Run one command using shell=True."""
    try:
        cwd = _resolve_cwd(temp_root, spec.cwd)
        completed = subprocess.run(
            spec.args,
            shell=True,
            cwd=os.fspath(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )  # nosec B602
    except BaseException as exc:
        return CommandResult(spec=spec, output="", returncode=None, error=repr(exc))

    return CommandResult(
        spec=spec, output=completed.stdout or "", returncode=completed.returncode, error=None
    )


def _execute(
    *, before_script: list[CommandSpec], script: list[CommandSpec], after_script: list[CommandSpec]
) -> RunResult:
    """Execute one directive in a temporary directory."""
    before_results: list[CommandResult] = []
    script_results: list[CommandResult] = []
    after_results: list[CommandResult] = []

    with tempfile.TemporaryDirectory(prefix="sphinx-docrun-") as tmp:
        temp_root = Path(tmp)

        try:
            for spec in before_script:
                result = _run_one(spec, temp_root=temp_root)
                before_results.append(result)
                if result.failed:
                    break

            if not any(result.failed for result in before_results):
                for spec in script:
                    result = _run_one(spec, temp_root=temp_root)
                    script_results.append(result)
                    if result.failed:
                        break

        finally:
            for spec in after_script:
                result = _run_one(spec, temp_root=temp_root)
                after_results.append(result)

    return RunResult(
        before_script=before_results, script=script_results, after_script=after_results
    )


def _apply_ellipsis(output: str, ellipsis: int | None) -> str:
    """Apply simple line-truncating ellipsis to output."""
    text = output.rstrip()
    if ellipsis is None:
        return text

    lines = text.splitlines()
    if ellipsis < len(lines):
        lines[ellipsis:] = ["..."]

    return "\n".join(lines)


def _render_transcript(script_results: list[CommandResult]) -> str:
    """Render main script commands as a console transcript."""
    chunks: list[str] = []

    for result in script_results:
        command = f"$ {result.spec.args}".rstrip()
        output = _apply_ellipsis(result.output, result.spec.ellipsis)

        if output:
            chunks.append(f"{command}\n{output}")
        else:
            chunks.append(command)

    return "\n\n".join(chunk for chunk in chunks if chunk).rstrip()


def _literal(text: str) -> nodes.literal_block:
    """Create a console literal block."""
    node = nodes.literal_block(text, text)
    node["language"] = "console"
    return node


def _render_nodes(transcript: str) -> list[nodes.Node]:
    """Return rendered nodes for a transcript."""
    if not transcript:
        return [nodes.meta()]
    return [_literal(transcript)]


def get_command_substitutions_from_conf(app: Any) -> dict[str, str]:
    """Return configured command substitutions.

    ``conf.py`` may define::

        docrun_command_substitutions = {
            "examples": "/path/to/examples",
        }

    Values are converted to strings so ``pathlib.Path`` values are accepted.
    """
    substitutions = getattr(app.config, "docrun_command_substitutions", None)
    if substitutions is None:
        return {}
    if not isinstance(substitutions, dict):
        raise TypeError("docrun_command_substitutions must be a dict[str, str]")
    return {str(key): str(value) for key, value in substitutions.items()}


def _expand_args(command: str, command_substitutions: dict[str, str]) -> str:
    """Expand template variables in a command args string."""
    context: dict[str, str] = dict(command_substitutions)
    try:
        return Template(command).safe_substitute(**context)
    except Exception as exc:
        logger.warning("Failed to expand template variables in command %r: %s", command, exc)
        return command


def _expand_specs(
    specs: list[CommandSpec], command_substitutions: dict[str, str]
) -> list[CommandSpec]:
    """Expand template variables in command args strings."""
    return [
        dataclasses.replace(spec, args=_expand_args(spec.args, command_substitutions))
        for spec in specs
    ]


def _cache_key(
    *,
    docname: str,
    before_script: list[CommandSpec],
    script: list[CommandSpec],
    after_script: list[CommandSpec],
) -> str:
    """Return the whole-directive cache key.

    The specs passed here should be raw, unexpanded specs from the directive.
    That keeps keys stable across machines and checkout locations.
    """
    payload = {
        "schema": CACHE_SCHEMA,
        "execution_model": EXECUTION_MODEL,
        "docname": docname,
        "before_script": [spec.to_json_obj() for spec in before_script],
        "script": [spec.to_json_obj() for spec in script],
        "after_script": [spec.to_json_obj() for spec in after_script],
    }

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _format_command_failure(phase: str, index: int, result: CommandResult) -> str:
    """Format one failed command for diagnostics."""
    actual = "not run" if result.returncode is None else str(result.returncode)

    parts = [
        f"{phase}[{index}] failed",
        f"  args: {result.spec.args!r}",
        f"  cwd: {result.spec.cwd!r}",
        f"  expected return code: {result.spec.returns}",
        f"  actual return code: {actual}",
    ]

    if result.error:
        parts.extend(["  error:", result.error])

    if result.output:
        parts.extend(["  output:", result.output.rstrip()])

    return "\n".join(parts)


def _failure_message(result: RunResult) -> str | None:
    """Return diagnostic text if a run failed."""
    failures: list[str] = []

    for i, command_result in enumerate(result.before_script):
        if command_result.failed:
            failures.append(_format_command_failure("before_script", i, command_result))
            break

    for i, command_result in enumerate(result.script):
        if command_result.failed:
            failures.append(_format_command_failure("script", i, command_result))
            break

    for i, command_result in enumerate(result.after_script):
        if command_result.failed:
            failures.append(_format_command_failure("after_script", i, command_result))

    if not failures:
        return None

    return "doc-run command failure:\n\n" + "\n\n".join(failures)


def _error_node(
    doctree: nodes.document, node: doc_run_output, message: str
) -> nodes.system_message:
    """Create a Sphinx/docutils error node."""
    error = doctree.reporter.error(message, base_node=node)
    error["level"] = 6
    return error


def _doc_source_dir(app: Any, docname: str) -> str:
    """Return directory containing the current RST source document."""
    source_file = Path(app.env.srcdir) / f"{docname}.rst"
    return os.fspath(source_file.parent)


def traverse(node: nodes.Node, arg: Any) -> Iterable[nodes.Node]:
    """Return matching descendants using docutils/Sphinx-compatible traversal."""
    if hasattr(node, "findall"):
        return node.findall(arg)
    return node.traverse(arg)


class DocRunDirective(rst.Directive):
    """Implementation for ``.. doc-run::``."""

    has_content = False
    final_argument_whitespace = False
    required_arguments = 0

    option_spec = {
        "before_script": _commands_json,
        "script": _commands_json,
        "after_script": _commands_json,
    }

    def run(self) -> list[nodes.Node]:
        """Parse directive options and create a placeholder node."""
        sphinx_env = self.state.document.settings.env
        docname = sphinx_env.docname

        if "script" not in self.options:
            raise self.error("doc-run requires the :script: option")

        script: list[CommandSpec] = list(self.options["script"])
        if not script:
            raise self.error("doc-run requires at least one script command")

        before_script: list[CommandSpec] = list(self.options.get("before_script") or [])
        after_script: list[CommandSpec] = list(self.options.get("after_script") or [])

        node = doc_run_output()
        node.line = self.lineno
        node["docname"] = docname
        node["before_script"] = [spec.to_json_obj() for spec in before_script]
        node["script"] = [spec.to_json_obj() for spec in script]
        node["after_script"] = [spec.to_json_obj() for spec in after_script]

        return [node]


def run_doc_commands(app: Any, doctree: nodes.document) -> None:
    """Execute or cache-hit all doc-run placeholder nodes."""
    cache: DocRunCache = app.env.docrun_cache
    cache.ensure_split(found_docs=set(app.env.found_docs))
    user_subs = get_command_substitutions_from_conf(app)

    for node in list(traverse(doctree, doc_run_output)):
        assert isinstance(node, doc_run_output)

        docname = str(node["docname"])
        doc_source_dir = _doc_source_dir(app, docname)
        doc_name = os.path.splitext(docname)[0]

        raw_before_script = _command_specs_from_node(node, "before_script")
        raw_script = _command_specs_from_node(node, "script")
        raw_after_script = _command_specs_from_node(node, "after_script")

        key = _cache_key(
            docname=docname,
            before_script=raw_before_script,
            script=raw_script,
            after_script=raw_after_script,
        )

        cached_transcript = cache.get(key)
        if cached_transcript is not None:
            logger.info("[doc-run] cache hit: %s %s", docname, key[:12])
            node.replace_self(_render_nodes(cached_transcript))
            continue

        logger.info("[doc-run] cache miss: %s %s", docname, key[:12])

        command_substitutions = user_subs | {"doc_source_dir": doc_source_dir, "doc_name": doc_name}
        before_script = _expand_specs(raw_before_script, command_substitutions)
        script = _expand_specs(raw_script, command_substitutions)
        after_script = _expand_specs(raw_after_script, command_substitutions)

        result = _execute(before_script=before_script, script=script, after_script=after_script)

        if message := _failure_message(result):
            node.replace_self(_error_node(doctree, node, message))
            continue

        transcript = _render_transcript(result.script)
        cache.put(key, docname=docname, transcript=transcript)
        node.replace_self(_render_nodes(transcript))


def init_cache(app: Any) -> None:
    """Load the original cache file.

    The loaded cache is split later, once Sphinx tells us which documents it
    will process in this build.
    """
    cache_path = Path(app.env.srcdir) / CACHE_FILENAME
    original_entries: dict[str, Any] = {}
    if os.environ.get("DOCRUN_REFRESH_CACHE"):
        logger.warning(
            "[doc-run] DOCRUN_REFRESH_CACHE is set; ignoring existing cache and rebuilding"
        )
        app.env.docrun_cache = DocRunCache(cache_path, original_entries)
        return

    if cache_path.exists():
        try:
            with cache_path.open(encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            logger.warning("Ignoring unreadable doc-run cache file %s: %s", cache_path, exc)
        else:
            if (
                isinstance(payload, dict)
                and payload.get("schema") == CACHE_SCHEMA
                and payload.get("execution_model") == EXECUTION_MODEL
                and isinstance(payload.get("entries"), dict)
            ):
                original_entries = dict(payload["entries"])
                logger.info(
                    "[doc-run] loaded cache: entries=%d path=%s", len(original_entries), cache_path
                )
            else:
                logger.warning("Ignoring incompatible doc-run cache file %s", cache_path)

    app.env.docrun_cache = DocRunCache(cache_path, original_entries)


def split_cache_for_docs(app: Any, env: Any, docnames: list[str] | set[str]) -> None:
    """Split cache by the documents Sphinx is about to process."""
    cache = getattr(env, "docrun_cache", None)
    if cache is None:
        return

    cache.split_for_docs(docnames_to_process=set(docnames), found_docs=set(env.found_docs))


def save_cache(app: Any, exception: BaseException | None) -> None:
    """Write the updated cache after a successful build."""
    if exception is not None:
        logger.warning("Build failed; not updating doc-run cache")
        return

    cache = getattr(app.env, "docrun_cache", None)
    if cache is None:
        return

    cache.write()


def setup(app: Any) -> dict[str, bool]:
    """Register directive and Sphinx event hooks."""
    app.add_directive("doc-run", DocRunDirective)
    app.connect("builder-inited", init_cache)
    app.connect("env-before-read-docs", split_cache_for_docs)
    app.connect("doctree-read", run_doc_commands)
    app.connect("build-finished", save_cache)
    app.add_config_value("docrun_command_substitutions", {}, "env")

    return {"parallel_read_safe": False, "parallel_write_safe": False}
