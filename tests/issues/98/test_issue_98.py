import pluggy
import pytest

import canary

hookspec = pluggy.HookspecMarker("canary")
hookimpl = pluggy.HookimplMarker("canary")


class Spec:
    @hookspec
    def canary_addoption(self, parser) -> None:  # use your real Parser type if importable
        """Allow plugins to add CLI options."""


class Plugin:
    @hookimpl
    def canary_addoption(self, parser: canary.Parser) -> None:
        parser.add_plugin_argument(
            "--tolerance",
            help="Tolerance when analyzing results against a baseline",
            type=float,
            default=1e-8,
        )


def test_canary_addoption_adds_tolerance_option() -> None:
    pm = pluggy.PluginManager("canary")
    pm.add_hookspecs(Spec)

    plugin = Plugin()
    pm.register(plugin)

    parser = canary.Parser()
    pm.hook.canary_addoption(parser=parser)

    ns = parser.parse_args([])
    assert ns.tolerance == pytest.approx(1e-8)

    ns = parser.parse_args(["--tolerance", "1e-6"])
    assert ns.tolerance == pytest.approx(1e-6)
