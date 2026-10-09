# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import _canary.util.testing as testing
from _canary.util import json_helper
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


def test_safesave_and_safeload_roundtrip(tmp_path: Path):
    path = tmp_path / "nested" / "state.json"
    state = {"a": 1, "b": {"c": [1, 2, 3]}}

    json_helper.safesave(str(path), state)

    assert path.exists()
    assert json_helper.safeload(str(path)) == state


def test_safesave_removes_tmp_file(tmp_path: Path):
    path = tmp_path / "state.json"
    json_helper.safesave(str(path), {"ok": True})

    assert not (tmp_path / ".state.json.tmp").exists()


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record the delays ``safeload`` sleeps for, without actually sleeping."""
    calls: list[float] = []
    monkeypatch.setattr(json_helper.time, "sleep", calls.append)
    return calls


def test_safeload_missing_file_retries_once_then_raises(tmp_path: Path, sleeps):
    with pytest.raises(FileNotFoundError):
        json_helper.safeload(str(tmp_path / "missing.json"))
    assert sleeps == [json_helper.SAFELOAD_MISSING_RETRY_DELAY]
    assert json_helper.SAFELOAD_MISSING_RETRY_DELAY <= 0.1


def test_safeload_missing_file_retry_ignores_attempts(tmp_path: Path, sleeps):
    with pytest.raises(FileNotFoundError):
        json_helper.safeload(str(tmp_path / "missing.json"), attempts=0)
    assert sleeps == [json_helper.SAFELOAD_MISSING_RETRY_DELAY]


def test_safeload_missing_file_that_appears_on_retry(tmp_path: Path, monkeypatch):
    """A file renamed into place by another process during the retry delay is loaded."""
    path = tmp_path / "late.json"

    def write_then_return(_delay: float) -> None:
        json_helper.safesave(str(path), {"late": True})

    monkeypatch.setattr(json_helper.time, "sleep", write_then_return)
    assert json_helper.safeload(str(path)) == {"late": True}


def test_safeload_corrupt_file_retries_with_bounded_backoff(tmp_path: Path, sleeps):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json")
    with pytest.raises(json_helper.FailedToLoadError) as excinfo:
        json_helper.safeload(str(path))
    assert isinstance(excinfo.value.__cause__, json.JSONDecodeError)
    assert sleeps == [0.05, 0.1, 0.2, 0.4]
    assert all(delay <= json_helper.SAFELOAD_MAX_DELAY for delay in sleeps)
    assert sum(sleeps) < 1.0


def test_safeload_backoff_is_capped(tmp_path: Path, sleeps):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json")
    with pytest.raises(json_helper.FailedToLoadError):
        json_helper.safeload(str(path), attempts=6)
    assert sleeps == [0.05, 0.1, 0.2, 0.4, 0.5, 0.5]


def test_safeload_recovers_when_file_becomes_valid(tmp_path: Path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("{partial")

    def fix_file(_delay: float) -> None:
        path.write_text('{"ok": true}')

    monkeypatch.setattr(json_helper.time, "sleep", fix_file)
    assert json_helper.safeload(str(path)) == {"ok": True}


def test_safeload_does_not_retry_non_transient_errors(tmp_path: Path, sleeps, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"ok": true}')

    def boom(_fh):
        raise ValueError("cannot deserialize")

    monkeypatch.setattr(json_helper, "load", boom)
    with pytest.raises(json_helper.FailedToLoadError, match="cannot deserialize"):
        json_helper.safeload(str(path))
    assert sleeps == []


def test_safeload_raises_after_retries(tmp_path: Path, sleeps):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json")

    # attempts=0: a single read, no retries and no sleep.
    with pytest.raises(json_helper.FailedToLoadError, match="after 1 attempt"):
        json_helper.safeload(str(path), attempts=0)
    assert sleeps == []


def test_safesave_supports_canary_serializable_object(tmp_path):
    from _canary.core.jobspec import Mask

    path = tmp_path / "state.json"
    state = Mask.masked("because")

    json_helper.safesave(path, state)

    out = json_helper.loads(path.read_text())
    assert out == state
