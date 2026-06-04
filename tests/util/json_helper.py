import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import _canary.util.testing as testing
from _canary.util.json_helper import Encoder
from _canary.util.json_helper import object_hook


def dumps(obj: Any) -> str:
    return json.dumps(obj, cls=Encoder, indent=2, sort_keys=True)


def loads(s: str) -> Any:
    return json.loads(s, object_hook=object_hook)


def roundtrip(obj: Any) -> Any:
    return loads(dumps(obj))


def test_roundtrip_plain_dict_no_type_tag():
    obj = {"a": 1, "b": {"c": 2}}
    out = roundtrip(obj)
    assert out == obj
    assert "__type__" not in out
    assert "__type__" not in out["b"]


def test_roundtrip_path_serializes_to_string():
    obj = {"p": Path("a/b/c.txt")}
    out = roundtrip(obj)
    assert out == {"p": "a/b/c.txt"}  # Path -> str; does not reconstruct Path


def test_roundtrip_tuple_serializes_to_list():
    obj = {"t": (1, 2, 3)}
    out = roundtrip(obj)
    assert out == {"t": [1, 2, 3]}  # tuple -> list; does not reconstruct tuple


# --- Custom types exercising __serialize__/__deserialize__ ---


@dataclass(frozen=True)
class Simple:
    x: int
    y: str

    def __serialize__(self):
        return {"x": self.x, "y": self.y}

    @classmethod
    def __deserialize__(cls, payload: dict):
        return cls(**payload)


def test_roundtrip_custom_type_simple():
    obj = Simple(3, "hi")
    out = roundtrip(obj)
    assert out == obj


def test_roundtrip_nested_custom_type_inside_dict_and_list():
    obj = {"items": [Simple(1, "a"), Simple(2, "b")], "n": 7}
    out = roundtrip(obj)
    assert out == obj


class WithNestedClass:
    @dataclass(frozen=True)
    class Inner:
        z: int

        def __serialize__(self):
            return {"z": self.z}

        @classmethod
        def __deserialize__(cls, payload: dict):
            return cls(**payload)


def test_roundtrip_custom_type_nested_qualname():
    obj = WithNestedClass.Inner(10)
    out = roundtrip(obj)
    assert out == obj


def test_type_tag_present_in_encoded_json_for_custom_type():
    s = dumps(Simple(1, "x"))
    d = json.loads(s)  # no hook: inspect raw payload
    assert d["__type__"].endswith("::Simple")
    assert d["x"] == 1
    assert d["y"] == "x"


def test_object_hook_ignores_dicts_without_type():
    d = {"x": 1, "y": 2, "__type__x": "not-a-type-tag"}
    out = json.loads(json.dumps(d), object_hook=object_hook)
    assert out == d


def test_object_hook_preserves_type_payload_copy_semantics():
    # Ensure object_hook doesn't mutate caller-provided dict (defensive).
    raw = {"x": 1, "y": "a", "__type__": f"{Simple.__module__}::{Simple.__qualname__}"}
    raw_copy = dict(raw)
    out = object_hook(raw)
    assert out == Simple(1, "a")
    assert raw == raw_copy


def test_object_hook_raises_on_bad_class_spec():
    bad = {"__type__": "nope", "x": 1}
    with pytest.raises(ValueError):
        object_hook(bad)


def test_object_hook_raises_on_missing_deserialize():
    class NoDeserialize:
        def __serialize__(self):
            return {"a": 1}

    payload = {"a": 1, "__type__": f"{NoDeserialize.__module__}::{NoDeserialize.__qualname__}"}
    with pytest.raises(AttributeError):
        object_hook(payload)


def test_jobspec(tmp_path: Path):
    jobs = testing.generate_random_jobspecs(root=tmp_path, count=1)
    for job in jobs:
        print(dumps(job))
        jj = roundtrip(job)
        assert jj == job
