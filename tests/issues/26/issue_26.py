import os

import _nvtest.plugins.nvtest_ctest.generator as ctg


def test_issue_26():
    file = os.path.join(os.path.dirname(__file__), "CTestTestfile.cmake")
    tests = ctg.load(file)
    test = tests["my-test"]
    for prop in test["properties"]:
        if prop["name"] == "PASS_REGULAR_EXPRESSION":
            break
    else:
        assert 0, "property not found"
    assert prop["value"] == ["this test has a new\nline", "and another\none"]
