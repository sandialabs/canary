# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.util.string import csvsplit
from _canary.util.string import strip_quotes
from _canary.util.string import truncate_middle


def test_strip_quotes():
    s = "a string"
    assert strip_quotes(f"""'''{s}'''""") == s
    assert strip_quotes(f"""'{s}'""") == s
    assert strip_quotes(f'''"""{s}"""''') == s
    assert strip_quotes(f'''"{s}"''') == s


def test_csvsplit():
    x = csvsplit("-a=b,-c='d,e,f',-g=h") == ["-a=b", "-c='d,e,f'", "-g=h"]
    x = csvsplit("-a=b,-c='\"d,e,f\"',-g=h") == ["-a=b", "-c='\"d,e,f\"'", "-g=h"]
    x = csvsplit("-a=b,-c=\"'d,e,f'\",-g=h") == ["-a=b", "-c=\"'d,e,f'\"", "-g=h"]
    with pytest.raises(ValueError):
        # mismatched quotes
        csvsplit("-a=b,-c='\"d,e,f'")


def test_truncate_middle_no_change_when_short() -> None:
    assert truncate_middle("abc", max_length=10) == "abc"


def test_truncate_middle_truncates_and_preserves_total_length() -> None:
    s = "abcdefghijklmnopqrstuvwxyz"
    out = truncate_middle(s, max_length=10, sep="...")
    assert out == "abc...wxyz"
    assert len(out) == 10


def test_truncate_middle_max_length_equals_len_sep() -> None:
    assert truncate_middle("abcdefghijklmnopqrstuvwxyz", max_length=3, sep="...") == "..."


def test_truncate_middle_max_length_less_than_len_sep() -> None:
    assert truncate_middle("abcdefghijklmnopqrstuvwxyz", max_length=2, sep="...") == ".."


def test_truncate_middle_raises_on_empty_sep() -> None:
    with pytest.raises(ValueError, match="sep must be a non-empty string"):
        truncate_middle("abc", max_length=2, sep="")
