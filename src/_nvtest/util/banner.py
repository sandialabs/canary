from itertools import cycle

from ..third_party import art
from ..third_party.color import colorize


def banner(color: bool = True) -> str:
    a = art.text2art("nvtest", "random")
    if not color:
        return a
    colors = cycle(["c", "c", "b", "b", "m", "m", "G", "G"])
    lines: list[str] = []
    for line in a.splitlines():
        if not line.split() and not lines:
            continue
        elif line.split():
            line = colorize("@*%s{%s}" % (next(colors), line))
        lines.append(line)
    return "\n".join(lines).rstrip()
