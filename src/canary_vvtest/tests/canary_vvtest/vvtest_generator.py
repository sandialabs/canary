# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import _canary.config as config
from _canary import rules
from _canary import select
from _canary import workspace
from _canary.generate import Generator
from _canary.util.filesystem import working_dir


def select_specs(
    specs,
    *,
    keyword_exprs=None,
    parameter_expr=None,
    owners=None,
    regex=None,
    ids=None,
    prefixes=None,
):
    selector = select.Selector(specs, workspace=Path.cwd())
    if keyword_exprs:
        selector.add_rule(rules.KeywordRule(keyword_exprs))
    if parameter_expr:
        selector.add_rule(rules.ParameterRule(parameter_expr))
    if owners:
        selector.add_rule(rules.OwnersRule(owners))
    if regex:
        selector.add_rule(rules.RegexRule(regex))
    if ids:
        selector.add_rule(rules.IDsRule(ids))
    if prefixes:
        selector.add_rule(rules.PrefixRule(prefixes))
    selector.run()
    return [spec for spec in selector.specs if not spec.mask]


def generate_specs(generators, on_options=None):
    generator = Generator(generators=generators, workspace=Path.cwd(), on_options=on_options or [])
    specs = generator.run()
    return specs


def test_vvt_generator(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        with open("test.vvt", "w") as fh:
            fh.write(
                """
# VVT: name: baz
# VVT: analyze : --analyze
# VVT: keywords: test unit
# VVT: parameterize (options=baz) : np=1 2
# VVT: parameterize : a,b,c=1,11,111 2,22,222 3,33,333
"""
            )
        with config.override():
            generators = workspace.find_generators_in_path(".")
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"])
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 7

            # without the baz option, the `np` parameter will not be expanded so we will be left with
            # three test cases and one analyze.  The analyze will not be masked because the `np`
            # parameter is never expanded
            specs = generate_specs(generators)
            assert specs[-1].attributes.get("multicase") is not None
            assert len(specs) == 4
            final = select_specs(specs, keyword_exprs=["test and unit"])
            assert len(final) == 4

            # with np<2, some of the cases will be filtered
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"], parameter_expr="np < 2")
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 3

            # this should also work with cpus < 2 since the vvtest plugin maps np to cpus
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"], parameter_expr="cpus < 2")
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is not None
            assert len(final) == 3
