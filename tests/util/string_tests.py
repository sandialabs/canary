import pytest

from _canary.util.string import csvsplit
from _canary.util.string import strip_quotes


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
