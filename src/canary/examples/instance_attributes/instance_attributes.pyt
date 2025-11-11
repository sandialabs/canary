#!/usr/bin/env python3

import json

import canary


def test():
    instance = canary.get_instance()
    instance.set_attribute(attribute=23)
    instance.save()

    with open("testcase.lock", "r") as fh:
        data = json.load(fh)
    assert data["spec"]["attributes"]["attribute"] == 23


if __name__ == "__main__":
    test()
