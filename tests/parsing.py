import argparse


def test_batch_args():
    import _nvtest.plugins.commands.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
    args = parser.parse_args(
        [
            "-l",
            "batch:args=--account=XYZ123",
            "-l",
            "batch:args=--licenses=pscratch",
            "-l",
            "batch:args=--foo=bar --baz=spam",
            "-l",
            "batch:args='--a=b -c d'",
        ]
    )
    assert args.rh["batch:runner_args"] == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c",
        "d",
    ]
    assert args.rh["batch:batched"] is True
    assert args.batched_invocation is True
