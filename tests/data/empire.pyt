#!/usr/bin/env python3
import sys

import nvtest

nvtest.directives.enable(
    True,
    when="testname='not run_cable_pregen' platforms='TLCC2 or CTS1 or ceelan or iDarwin'",
)
nvtest.directives.enable(True, when="testname=run_cable_pregen")
nvtest.directives.parameterize(
    "cable",
    ["Powerbus2", "RG402"],
    when="testname='not run_cable_pregen or not sver_pregen'",
)
nvtest.directives.parameterize(
    "cable", ["Powerbus2"], when="testname='run_cable_pregen or sver_pregen'"
)
nvtest.directives.parameterize(
    "spectrum",
    [
        "Pithon7789",
        "Unfold-spectrum-7789",
        "Pithon7789-AXIOM-Unfold",
        "Pithon7789-AXIOM-Unfold-UQ",
    ],
    when="testname='not run_cubit and not run_seacas and not run_cable_pregen and not sver_pregen'",
)
nvtest.directives.parameterize(
    "spectrum", ["Pithon7789"], when="testname='run_cable_pregen or sver_pregen'"
)
nvtest.directives.parameterize(
    "mesh_level",
    [1],
    when="testname='run_cubit or run_seacas or run_sceptre or run_cable or plot_cable'",
)
nvtest.directives.parameterize("mesh_level", [1, 2, 3], when="testname=run_cable_pregen")
nvtest.directives.link("../../preload")
nvtest.directives.name("create_inputs")
nvtest.directives.preload("source-script preload/empire_env.sh", when="testname=create_inputs")
nvtest.directives.link("spectra", "cables", when="testname=create_inputs")
nvtest.directives.timeout(300, when="testname=create_inputs")
nvtest.directives.keywords("cce", when="testname=create_inputs")
nvtest.directives.parameterize("np", [1], when="testname=create_inputs")
nvtest.directives.name("run_cepxs")
nvtest.directives.preload("source-script preload/sceptre_env.sh", when="testname=run_cepxs")
nvtest.directives.depends_on(
    "create_inputs.*cable=${cable}*.spectrum=${spectrum}",
    when="testname=run_cepxs",
    expect=1,
    result="pass",
)
nvtest.directives.timeout(300, when="testname=run_cepxs")
nvtest.directives.keywords("cce", "cepxs", when="testname=run_cepxs")
nvtest.directives.parameterize("np", [1], when="testname=run_cepxs")
nvtest.directives.name("run_cubit")
nvtest.directives.link("cables", when="testname=run_cubit")
nvtest.directives.preload("source-script preload/empire_env.sh", when="testname=run_cubit")
nvtest.directives.timeout(300, when="testname=run_cubit")
nvtest.directives.keywords("cce", "cubit", when="testname=run_cubit")
nvtest.directives.parameterize("np", [1], when="testname=run_cubit")
nvtest.directives.name("run_seacas")
nvtest.directives.depends_on(
    "run_cubit.*cable=${cable}.*mesh_level=${mesh_level}*",
    when="testname=run_seacas",
    expect=1,
    result="pass",
)
nvtest.directives.preload("source-script preload/empire_env.sh", when="testname=run_seacas")
nvtest.directives.timeout(300, when="testname=run_seacas")
nvtest.directives.keywords("cce", "seacas", when="testname=run_seacas")
nvtest.directives.parameterize("np", [1], when="testname=run_seacas")
nvtest.directives.parameterize("target_np", [72], when="testname=run_seacas platforms='not TLCC2'")
nvtest.directives.parameterize("target_np", [64], when="testname=run_seacas platforms=TLCC2")
nvtest.directives.name("run_sceptre")
nvtest.directives.depends_on(
    "create_inputs.*cable=${cable}.*spectrum=${spectrum}",
    when="testname=run_sceptre",
    expect=1,
    result="pass",
)
nvtest.directives.depends_on(
    "run_seacas.*cable=${cable}.*mesh_level=${mesh_level}.*target_np=${np}",
    when="testname=run_sceptre",
    expect=1,
    result="pass",
)
nvtest.directives.depends_on(
    "run_cepxs.*cable=${cable}.*spectrum=${spectrum}",
    when="testname=run_sceptre",
    expect=1,
    result="pass",
)
nvtest.directives.preload("source-script preload/sceptre_env.sh", when="testname=run_sceptre")
nvtest.directives.timeout(10800, when="testname=run_sceptre")
nvtest.directives.keywords("cce", "sceptre", when="testname=run_sceptre")
nvtest.directives.parameterize("np", [72], when="testname=run_sceptre platforms='not TLCC2'")
nvtest.directives.parameterize("np", [64], when="testname=run_sceptre platforms=TLCC2")
nvtest.directives.name("run_cable")
nvtest.directives.name("run_cable_pregen")
nvtest.directives.depends_on(
    "run_sceptre.*cable=${cable}.*mesh_level=${mesh_level}.*spectrum=${spectrum}",
    when="testname=run_cable",
    expect=1,
    result="pass",
)
nvtest.directives.depends_on(
    "create_inputs.*cable=${cable}.*spectrum=${spectrum}",
    when="testname='run_cable*'",
    expect=1,
    result="pass",
)
nvtest.directives.preload("source-script preload/empire_env.sh", when="testname='run_cable*'")
nvtest.directives.keywords("cce", when="testname='run_cable*'")
nvtest.directives.timeout(900, when="testname='run_cable*'")
nvtest.directives.link("cables", "spectra", "experiments", when="testname='run_cable*'")
nvtest.directives.link("pregen", when="testname=run_cable_pregen")
nvtest.directives.parameterize("np", [4], when="testname=run_cable")
nvtest.directives.parameterize("np", [1], when="testname=run_cable_pregen")
nvtest.directives.name("sver_pregen")
nvtest.directives.depends_on(
    "run_cable_pregen.*cable=${cable}.*spectrum=${spectrum}*",
    when="testname=sver_pregen",
    expect=3,
    result="pass",
)
nvtest.directives.preload("source-script preload/empire_env.sh", when="testname=sver_pregen")
nvtest.directives.keywords(
    "empire",
    "empire-cable",
    "cable",
    "fast",
    "small",
    "gpu",
    when="testname='sver_pregen*'",
)
nvtest.directives.parameterize("np", [1], when="testname=sver_pregen options='not gpu'")
nvtest.directives.parameterize("np,ndevice", [[1, 1]], when="testname=sver_pregen options=gpu")
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
