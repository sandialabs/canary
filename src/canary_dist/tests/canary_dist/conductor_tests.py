# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for canary_dist.conductor — pure functions only."""

import argparse

import pytest

from canary_dist.conductor import export_splitter
from canary_dist.conductor import DistributedPoolConductor


# ---------------------------------------------------------------------------
# export_splitter
# ---------------------------------------------------------------------------


def test_export_splitter_single_var():
    result = export_splitter("MY_VAR")
    assert result == {"MY_VAR": "==YES=="}


def test_export_splitter_var_equals_value():
    result = export_splitter("MY_VAR=hello")
    assert result == {"MY_VAR": "hello"}


def test_export_splitter_all():
    result = export_splitter("ALL")
    assert result == {"ALL": "==YES=="}


def test_export_splitter_all_clears_previous():
    # Once ALL is seen, earlier entries are cleared
    result = export_splitter("FOO,ALL")
    assert result == {"ALL": "==YES=="}
    assert "FOO" not in result


def test_export_splitter_all_stops_after():
    # ALL breaks immediately; later tokens are ignored
    result = export_splitter("ALL,BAR")
    assert result == {"ALL": "==YES=="}


def test_export_splitter_multiple_vars():
    result = export_splitter("A,B=1,C")
    assert result == {"A": "==YES==", "B": "1", "C": "==YES=="}


def test_export_splitter_empty_string():
    result = export_splitter("")
    assert result == {}


def test_export_splitter_whitespace_trimmed():
    result = export_splitter("  A  ,  B=2  ")
    assert result == {"A": "==YES==", "B": "2"}


def test_export_splitter_value_with_equals():
    # partition('=') → only first '=' splits
    result = export_splitter("URL=http://host:8080/path")
    assert result == {"URL": "http://host:8080/path"}


# ---------------------------------------------------------------------------
# validate_and_set_defaults
# ---------------------------------------------------------------------------


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def test_validate_raises_when_no_server():
    with pytest.raises(ValueError, match="missing required argument"):
        DistributedPoolConductor.validate_and_set_defaults(_ns())


def test_validate_passes_with_server_url():
    # Should not raise
    DistributedPoolConductor.validate_and_set_defaults(_ns(dist_server_url="http://host:1234"))


def test_validate_raises_count_and_duration_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        DistributedPoolConductor.validate_and_set_defaults(
            _ns(dist_server_url="http://h", dist_batch_count=5, dist_batch_duration=120)
        )


def test_validate_raises_count_zero():
    with pytest.raises(ValueError, match="must be > 0"):
        DistributedPoolConductor.validate_and_set_defaults(
            _ns(dist_server_url="http://h", dist_batch_count=0, dist_batch_duration=None)
        )


def test_validate_raises_count_negative():
    with pytest.raises(ValueError, match="must be > 0"):
        DistributedPoolConductor.validate_and_set_defaults(
            _ns(dist_server_url="http://h", dist_batch_count=-1, dist_batch_duration=None)
        )


def test_validate_raises_duration_zero():
    with pytest.raises(ValueError, match="must be > 0"):
        DistributedPoolConductor.validate_and_set_defaults(
            _ns(dist_server_url="http://h", dist_batch_count=None, dist_batch_duration=0.0)
        )


def test_validate_passes_count_only():
    DistributedPoolConductor.validate_and_set_defaults(
        _ns(dist_server_url="http://h", dist_batch_count=3, dist_batch_duration=None)
    )


def test_validate_passes_duration_only():
    DistributedPoolConductor.validate_and_set_defaults(
        _ns(dist_server_url="http://h", dist_batch_count=None, dist_batch_duration=60.0)
    )
