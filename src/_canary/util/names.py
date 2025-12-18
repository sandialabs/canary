# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from typing import Any
from typing import Iterable

import randomname

default_groups = ["a/colors", "n/apex_predators"]


def random_name(groups: Any = default_groups, seed: int | None = None) -> str:
    """Generate a random name with one random entry from each of the provided groups"""
    return randomname.generate(*groups, seed=seed)


def unique_random_name(
    existing_names: Iterable[str],
    max_samples: int = 20,
    groups: Any = default_groups,
    seed: int | None = None,
) -> str:
    """Attempt to generate a random name that is not in `existing_names` within `max_samples`.

    Raises `ValueError` if unable to generate a unique name
    """
    for _ in range(max_samples):
        name = random_name(groups=groups, seed=seed)
        if name not in existing_names:
            return name
    else:
        raise ValueError(
            f"unable to generate name outside {existing_names} in {max_samples} attempts"
        )
