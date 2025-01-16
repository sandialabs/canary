from _canary.util.string import strip_quotes


def test_strip_quotes():
    s = "a string"
    assert strip_quotes(f"""'''{s}'''""") == s
    assert strip_quotes(f"""'{s}'""") == s
    assert strip_quotes(f'''"""{s}"""''') == s
    assert strip_quotes(f'''"{s}"''') == s
