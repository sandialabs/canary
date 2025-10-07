from canary_cmake.ctest import validate_resource_specs


def test_ctest_schema():
    data = {
        "local": {
            "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
            "gpus": [{"id": "0", "slots": 1}],
        }
    }
    validate_resource_specs(data)
