# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""ext.pyt.directives.signatures matches the directives' real signatures."""

import inspect
import json
import re
from importlib import resources

import canary_pyt.directives as directives


def directive_signature(func) -> str:
    """The signature ext.pyt.directives shows: annotations shortened, no return type."""
    text = str(inspect.signature(func)).removesuffix(" -> None")
    text = text.replace("str | dict[str, str] | None", "WhenType | None")
    text = re.sub(r"\b_canary\.[\w.]+\.(\w+)", r"\1", text)
    text = text.replace("'enums.enums'", "ParameterSpace")
    text = text.replace("<enums.list_parameter_space: 0>", "list_parameter_space")
    return f"{func.__name__}{text}"


def test_directive_signatures_match_the_directives():
    data = json.loads(resources.files("canary_pyt.data").joinpath("capabilities.json").read_text())
    shown = data["capabilities"]["directives"]["signatures"]
    assert {"depends_on", "copy", "artifact", "skipif", "aggregate"} <= set(shown)
    for name, signature in shown.items():
        assert signature == directive_signature(getattr(directives, name)), name
