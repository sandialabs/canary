#!/usr/bin/env python3
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import sys

import canary_pyt

canary_pyt.directives.enable(
    True,
    when="testname='not run_cable_pregen' platforms='TLCC2 or CTS1 or ceelan or iDarwin'",
)
canary_pyt.directives.enable(True, when="testname=run_cable_pregen")
canary_pyt.directives.parameterize(
    "cable",
    ["Powerbus2", "RG402"],
    when="testname='not run_cable_pregen or not sver_pregen'",
)
canary_pyt.directives.parameterize(
    "cable", ["Powerbus2"], when="testname='run_cable_pregen or sver_pregen'"
)
canary_pyt.directives.parameterize(
    "spectrum",
    [
        "Pithon7789",
        "Unfold-spectrum-7789",
        "Pithon7789-AXIOM-Unfold",
        "Pithon7789-AXIOM-Unfold-UQ",
    ],
    when="testname='not run_cubit and not run_seacas and not run_cable_pregen and not sver_pregen'",
)
canary_pyt.directives.parameterize(
    "spectrum", ["Pithon7789"], when="testname='run_cable_pregen or sver_pregen'"
)
canary_pyt.directives.parameterize(
    "mesh_level",
    [1],
    when="testname='run_cubit or run_seacas or run_sceptre or run_cable or plot_cable'",
)
canary_pyt.directives.parameterize("mesh_level", [1, 2, 3], when="testname=run_cable_pregen")
canary_pyt.directives.link("../../preload")
canary_pyt.directives.name("create_inputs")
canary_pyt.directives.preload("source-script preload/empire_env.sh", when="testname=create_inputs")
canary_pyt.directives.link("spectra", "cables", when="testname=create_inputs")
canary_pyt.directives.timeout(300, when="testname=create_inputs")
canary_pyt.directives.keywords("cce", when="testname=create_inputs")
canary_pyt.directives.parameterize("cpus", [1], when="testname=create_inputs")
canary_pyt.directives.name("run_cepxs")
canary_pyt.directives.preload("source-script preload/sceptre_env.sh", when="testname=run_cepxs")
canary_pyt.directives.depends_on(
    {"job": "create_inputs.*cable=${cable}*.spectrum=${spectrum}", "expects": 1, "when": "on_success"},
    when="testname=run_cepxs",
)
canary_pyt.directives.timeout(300, when="testname=run_cepxs")
canary_pyt.directives.keywords("cce", "cepxs", when="testname=run_cepxs")
canary_pyt.directives.parameterize("cpus", [1], when="testname=run_cepxs")
canary_pyt.directives.name("run_cubit")
canary_pyt.directives.link("cables", when="testname=run_cubit")
canary_pyt.directives.preload("source-script preload/empire_env.sh", when="testname=run_cubit")
canary_pyt.directives.timeout(300, when="testname=run_cubit")
canary_pyt.directives.keywords("cce", "cubit", when="testname=run_cubit")
canary_pyt.directives.parameterize("cpus", [1], when="testname=run_cubit")
canary_pyt.directives.name("run_seacas")
canary_pyt.directives.depends_on(
    {"job": "run_cubit.*cable=${cable}.*mesh_level=${mesh_level}*", "expects": 1, "when": "on_success"},
    when="testname=run_seacas",
)
canary_pyt.directives.preload("source-script preload/empire_env.sh", when="testname=run_seacas")
canary_pyt.directives.timeout(300, when="testname=run_seacas")
canary_pyt.directives.keywords("cce", "seacas", when="testname=run_seacas")
canary_pyt.directives.parameterize("cpus", [1], when="testname=run_seacas")
canary_pyt.directives.parameterize("target_np", [72], when="testname=run_seacas platforms='not TLCC2'")
canary_pyt.directives.parameterize("target_np", [64], when="testname=run_seacas platforms=TLCC2")
canary_pyt.directives.name("run_sceptre")
canary_pyt.directives.depends_on(
    {"job": "create_inputs.*cable=${cable}.*spectrum=${spectrum}", "expects": 1, "when": "on_success"},
    when="testname=run_sceptre",
)
canary_pyt.directives.depends_on(
    {"job": "run_seacas.*cable=${cable}.*mesh_level=${mesh_level}.*target_np=${cpus}", "expects": 1, "when": "on_success"},
    when="testname=run_sceptre",
)
canary_pyt.directives.depends_on(
    {"job": "run_cepxs.*cable=${cable}.*spectrum=${spectrum}", "expects": 1, "when": "on_success"},
    when="testname=run_sceptre",
)
canary_pyt.directives.preload("source-script preload/sceptre_env.sh", when="testname=run_sceptre")
canary_pyt.directives.timeout(10800, when="testname=run_sceptre")
canary_pyt.directives.keywords("cce", "sceptre", when="testname=run_sceptre")
canary_pyt.directives.parameterize("cpus", [72], when="testname=run_sceptre platforms='not TLCC2'")
canary_pyt.directives.parameterize("cpus", [64], when="testname=run_sceptre platforms=TLCC2")
canary_pyt.directives.name("run_cable")
canary_pyt.directives.name("run_cable_pregen")
canary_pyt.directives.depends_on(
    {"job": "run_sceptre.*cable=${cable}.*mesh_level=${mesh_level}.*spectrum=${spectrum}", "expects": 1, "when": "on_success"},
    when="testname=run_cable",
)
canary_pyt.directives.depends_on(
    {"job": "create_inputs.*cable=${cable}.*spectrum=${spectrum}", "expects": 1, "when": "on_success"},
    when="testname='run_cable*'",
)
canary_pyt.directives.preload("source-script preload/empire_env.sh", when="testname='run_cable*'")
canary_pyt.directives.keywords("cce", when="testname='run_cable*'")
canary_pyt.directives.timeout(900, when="testname='run_cable*'")
canary_pyt.directives.link("cables", "spectra", "experiments", when="testname='run_cable*'")
canary_pyt.directives.link("pregen", when="testname=run_cable_pregen")
canary_pyt.directives.parameterize("cpus", [4], when="testname=run_cable")
canary_pyt.directives.parameterize("cpus", [1], when="testname=run_cable_pregen")
canary_pyt.directives.name("sver_pregen")
canary_pyt.directives.depends_on(
    {"job": "run_cable_pregen.*cable=${cable}.*spectrum=${spectrum}*", "expects": 3, "when": "on_success"},
    when="testname=sver_pregen",
)
canary_pyt.directives.preload("source-script preload/empire_env.sh", when="testname=sver_pregen")
canary_pyt.directives.keywords(
    "empire",
    "empire-cable",
    "cable",
    "fast",
    "small",
    "gpu",
    when="testname='sver_pregen*'",
)
canary_pyt.directives.parameterize("cpus", [1], when="testname=sver_pregen options='not gpu'")
canary_pyt.directives.parameterize("cpus,gpus", [[1, 1]], when="testname=sver_pregen options=gpu")
sys.dont_write_bytecode = True

if __name__ == "__main__":
    import vvtest_util as vvt

    if vvt.NAME == "create_inputs":
        from workflow import create_inputs

        create_inputs.main(vvt)

    elif vvt.NAME == "run_cubit":
        from workflow import run_cubit

        run_cubit.main(vvt)
    elif vvt.NAME == "run_seacas":
        from workflow import run_seacas

        run_seacas.main(vvt)
    elif vvt.NAME == "run_cepxs":
        from workflow import run_cepxs

        run_cepxs.main(vvt)
    elif vvt.NAME == "run_sceptre":
        from workflow import run_sceptre

        run_sceptre.main(vvt)

    elif vvt.NAME in ["run_cable", "run_cable_pregen"]:
        from workflow import run_cable

        run_cable.main(vvt)

    elif vvt.NAME == "sver_pregen":
        from workflow import run_sver

        run_sver.main(vvt, two_d_convergence=False)
    else:
        raise Exception("Test name not recognized: " + vvt.NAME)
