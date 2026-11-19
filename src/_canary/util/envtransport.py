# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Safe transport of environment variables into generated batch scripts.

Scheduler backends write each variable into the batch script as
``export NAME="value"``.  Inside double quotes the shell still expands ``$``,
backticks and ``\\``, and a ``"`` ends the string -- so a value such as
``x"; rm -rf ~; "`` (or simply a JSON blob, a multi-line value, or a token
containing ``$``) either breaks the script or executes arbitrary commands.

:func:`pack_environment` keeps only values that are inert inside double quotes
and moves every other variable into a single base64-encoded payload
(``CANARY_ENV_B64``), which contains only ``[A-Za-z0-9+/=]``.  The canary
process started by the batch script calls :func:`restore_environment` at
startup to decode it, so values arrive byte-for-byte without depending on any
backend's quoting.

Secret-looking variables can be identified with :func:`is_secret_name` so that
callers can avoid persisting them (e.g. in ``env.json``).
"""

import base64
import json
import os
import re
from typing import Mapping
from typing import MutableMapping

#: Environment variable holding the encoded payload.
PAYLOAD_VAR = "CANARY_ENV_B64"

#: Valid POSIX shell variable names.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Characters that are inert inside a double-quoted shell string.
_SAFE_VALUE = re.compile(r'^[^"$`\\\x00-\x1f\x7f]*$')

#: Name components that indicate a credential.  Matched case-insensitively
#: against ``_``-separated name components (e.g. GITLAB_TOKEN, AWS_ACCESS_KEY_ID).
_SECRET_PARTS = frozenset(
    (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "PASSWD",
        "PASS",
        "PWD",
        "PASSPHRASE",
        "CREDENTIAL",
        "CREDENTIALS",
        "KEY",
        "APIKEY",
        "PAT",
        "JWT",
        "BEARER",
        "PRIVATE",
        "AUTH",
        "COOKIE",
        "SESSION",
    )
)

#: Suffixes that mark a credential even when fused into a longer component
#: (PGPASSWORD, GHTOKEN, CLIENTSECRET).  Suffix-only, so TOKENIZER is not a match.
_SECRET_SUFFIXES = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "APIKEY")

#: Names that match a secret component but are not credentials.
_NOT_SECRET_NAMES = frozenset(("PWD",))

#: The userinfo part (``user:password@``) of a URL embedded in a value.  Greedy up
#: to the last ``@`` before the host, so an unescaped ``@`` in a password is covered.
_URL_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s]*@")

#: Placeholder written in place of a redacted value.
REDACTED = "<redacted>"


def is_valid_name(name: str) -> bool:
    """True if *name* is a valid shell environment variable name."""
    return bool(_NAME.match(name))


def is_secret_name(name: str) -> bool:
    """Heuristically decide whether environment variable *name* holds a credential.

    Additional names can be listed (comma separated, ``fnmatch`` patterns
    allowed) in ``CANARY_SECRET_VARS``; names listed in ``CANARY_NOT_SECRET_VARS``
    are never treated as secret.
    """
    import fnmatch

    upper = name.upper()
    allow = [p.strip() for p in os.getenv("CANARY_NOT_SECRET_VARS", "").split(",") if p.strip()]
    if any(fnmatch.fnmatchcase(upper, p.upper()) for p in allow):
        return False
    extra = [p.strip() for p in os.getenv("CANARY_SECRET_VARS", "").split(",") if p.strip()]
    if any(fnmatch.fnmatchcase(upper, p.upper()) for p in extra):
        return True
    if upper in _NOT_SECRET_NAMES:
        return False
    parts = upper.split("_")
    return any(part in _SECRET_PARTS or part.endswith(_SECRET_SUFFIXES) for part in parts)


def redact_value(value: str) -> str:
    """Return *value* with credentials in embedded URLs (``scheme://user:pass@host``) redacted."""
    return _URL_USERINFO.sub(rf"\1{REDACTED}@", value)


def redact(env: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of *env* with secrets replaced by :data:`REDACTED`.

    Values of secret-looking variables are replaced whole; in all other values,
    credentials embedded in URLs (e.g. ``HTTPS_PROXY=http://user:pass@proxy``) are.
    """
    return {k: (REDACTED if is_secret_name(k) else redact_value(v)) for k, v in env.items()}


def pack_environment(env: Mapping[str, str | None]) -> dict[str, str | None]:
    """Return an environment mapping that is safe to write as ``export NAME="value"``.

    Variables whose values are inert inside double quotes are passed through.
    All others (and ``None``/unset requests, which are kept as-is) are encoded
    into :data:`PAYLOAD_VAR`.  Invalid variable names raise ``ValueError``.
    """
    out: dict[str, str | None] = {}
    packed: dict[str, str] = {}
    for name, value in env.items():
        if not is_valid_name(name):
            raise ValueError(f"Invalid environment variable name {name!r}")
        if name == PAYLOAD_VAR:
            continue
        if value is None or _SAFE_VALUE.match(value):
            out[name] = value
        else:
            packed[name] = value
    if packed:
        blob = json.dumps(packed, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        out[PAYLOAD_VAR] = base64.b64encode(blob).decode("ascii")
    return out


def restore_environment(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Decode :data:`PAYLOAD_VAR` (if present) into *environ*; return the restored names."""
    environ = os.environ if environ is None else environ
    blob = environ.pop(PAYLOAD_VAR, None)
    if not blob:
        return []
    try:
        data = json.loads(base64.b64decode(blob.encode("ascii"), validate=True).decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Malformed {PAYLOAD_VAR} payload: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"Malformed {PAYLOAD_VAR} payload: expected an object")
    restored: list[str] = []
    for name, value in data.items():
        if isinstance(name, str) and is_valid_name(name) and isinstance(value, str):
            environ[name] = value
            restored.append(name)
    return restored
