import shutil
import sys
from typing import IO
from typing import Any

# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------


def color(text: str, code: str) -> str:
    """Apply ANSI color if stdout is a terminal."""
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def green(text: str) -> str:
    return color(text, "32")


def red(text: str) -> str:
    return color(text, "31")


def yellow(text: str) -> str:
    return color(text, "33")


def cyan(text: str) -> str:
    return color(text, "36")


# ---------------------------------------------------------------------------
# Printing logic
# ---------------------------------------------------------------------------


def print_resource_pool_status(
    data: dict[str, Any], verbose: bool = False, file: IO[Any] = sys.stdout
) -> None:
    machines = data.get("machines", [])
    term_width = shutil.get_terminal_size((100, 20)).columns
    sep_line = "-" * term_width

    # Cluster-wide totals
    cluster_totals: dict[str, dict[str, int]] = {}

    # Pre-scan to build totals
    for machine in machines:
        for rtype, rlist in machine.get("resources", {}).items():
            total_slots = sum(r.get("slots", 1) for r in rlist)
            available_slots = sum(r.get("slots", 1) for r in rlist if r.get("slots", 0) > 0)
            agg = cluster_totals.setdefault(rtype, {"total": 0, "available": 0})
            agg["total"] += total_slots
            agg["available"] += available_slots

    # Print header and cluster summary
    file.write(cyan("Distributed Resource Pool") + "\n")
    file.write(sep_line + "\n")

    if cluster_totals:
        cluster_summary = []
        for rtype, vals in cluster_totals.items():
            total = vals["total"]
            avail = vals["available"]
            pct = int(round(100 * avail / total)) if total > 0 else 0
            color_fn = green if avail > 0 else red
            cluster_summary.append(f"{rtype}: total={total}, free={color_fn(str(avail))} ({pct}%)")
        file.write("Cluster totals: " + " | ".join(cluster_summary) + "\n")
        file.write(sep_line + "\n")

    # Per-machine summary
    for machine in machines:
        host = machine.get("hostname", "<unknown>")
        file.write(f"{yellow('Host:')} {host}\n")

        tags = machine.get("tags") or []
        file.write(f"  tags: {', '.join(tags)}\n")

        if groups := machine.get("groups"):
            file.write(f"  groups: {', '.join(groups)}\n")

        resources = machine.get("resources", {})
        # Per-host summary
        summary_parts = []
        for rtype, rlist in resources.items():
            total_slots = sum(r.get("slots", 1) for r in rlist)
            available_slots = sum(r.get("slots", 1) for r in rlist if r.get("slots", 0) > 0)
            pct = int(round(100 * available_slots / total_slots)) if total_slots > 0 else 0
            color_fn = green if available_slots > 0 else red
            summary_parts.append(
                f"{rtype}: total={total_slots}, free={color_fn(str(available_slots))} ({pct}%)"
            )

        if summary_parts:
            file.write("  " + " | ".join(summary_parts) + "\n")
        else:
            file.write("  (no resources)\n")

        # Optional verbose listing
        if verbose:
            for rtype, rlist in resources.items():
                file.write(f"  {rtype}:\n")
                row = []
                for res in rlist:
                    rid = res.get("id", "?")
                    slots = res.get("slots", 0)
                    entry = green(f"{rid}({slots})") if slots > 0 else red(f"{rid}({slots})")
                    row.append(entry)

                line = "  ".join(row)
                for chunk_start in range(0, len(line), term_width - 4):
                    file.write("    " + line[chunk_start : chunk_start + term_width - 4] + "\n")
        file.write("\n")

    file.write(sep_line + "\n")
