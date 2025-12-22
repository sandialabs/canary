#!/usr/bin/env python3
"""
Generate a large Canary test suite for performance testing.

- Generates tens of thousands of `.pyt` files
- Each file contains:
  - keywords()
  - a *single* parameterize() call with multiple parameters (no Cartesian product)
  - optional depends_on() using spec *names* (not IDs)
- Parameter names are sorted to ensure deterministic spec names
"""

import argparse
import io
import random
from pathlib import Path
from typing import Any
from typing import Iterable

PARAM_NAMES: list[str] = ["a", "b", "c", "x", "y", "z"]
KEYWORDS: list[str] = ["fast", "slow", "cpu", "gpu", "io", "stress"]


def chunked(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def main(outdir: Path, files: int, max_params: int, max_rows: int) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    filenames: list[str] = []

    for i in range(files):
        name = f"test_{i:06d}.pyt"
        filenames.append(name)

    cache: list[str] = []
    for group in chunked(filenames, 1_000):
        for fname in group:
            name = Path(fname).stem
            cache.append(name)

            num_params = random.randint(1, max_params)
            num_rows = random.randint(1, max_rows)

            names = sorted(random.sample(PARAM_NAMES, num_params))
            params = {n: list(range(num_rows)) for n in names}

            kws = random.sample(KEYWORDS, random.randint(0, 3))
            deps = []
            if random.random() < 0.2:
                dep = random.choice(cache)
                deps = [dep]

            fp = io.StringIO()
            fp.write("#/usr/bin/env python3\n")
            fp.write("import canary\n")
            if kws:
                fp.write(f"canary.directives.keywords({', '.join(repr(kw) for kw in kws)})\n")
            if params:
                p_names = ",".join(params.keys())
                p_values = list(zip(*params.values()))
                fp.write(f"canary.directives.parameterize('{p_names}', {p_values})\n")
                cache.extend(generate_spec_names(name, p_names, p_values))

            if deps:
                fp.write("\n".join(f"canary.directives.depends_on({dep!r})" for dep in deps))

            (outdir / fname).write_text(fp.getvalue())


def generate_spec_names(family: str, names: str, values: list[tuple[Any, ...]]) -> list[str]:
    param_names = [n.strip() for n in names.split(",")]
    if any(len(param_names) != len(v) for v in values):
        raise ValueError("Incorrect param name/value shape")
    names: list[str] = []
    for value in values:
        parts = [f"{name}={v}" for name, v in zip(param_names, value)]
        name = f"{family}.{'.'.join(sorted(parts))}"
        names.append(name)
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--count", type=int, default=50_000)
    parser.add_argument("--max-params", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=5)
    args = parser.parse_args()

    main(
        outdir=args.outdir,
        files=args.count,
        max_params=args.max_params,
        max_rows=args.max_rows,
    )
