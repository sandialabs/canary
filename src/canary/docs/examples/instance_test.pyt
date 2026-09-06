import canary
import canary_pyt


@canary_pyt.instance_test
def test_alpha(inst: canary.TestInstance) -> int:
    assert inst.family == "alpha"
    return 0


@canary_pyt.instance_test
def test_beta(inst: canary.TestInstance) -> int:
    assert inst.family == "beta"
    return 0
