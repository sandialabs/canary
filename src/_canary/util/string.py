# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""String manipulation utilities used throughout canary.

Key functions: ``csvsplit`` (comma-split respecting quotes), ``strip_quotes``,
``pluralize``, ``stringify``, ``truncate_middle``, and the ``SimpleTemplate``
class for ``$var`` / ``${var}`` substitution.
"""

import io
import re
import tokenize
from typing import Any
from typing import Generator
from typing import Mapping


def get_tokens(path) -> Generator[tokenize.TokenInfo, None, None]:
    """Tokenize a Python source string, yielding ``TokenInfo`` objects.

    Args:
        path: Source string to tokenize.

    Returns:
        Generator of ``tokenize.TokenInfo`` objects.
    """
    return tokenize.tokenize(io.BytesIO(path.encode("utf-8")).readline)


def strip_quotes(arg: str) -> str:
    """Remove surrounding quotes from a Python string literal token.

    Handles single, double, triple-single, and triple-double quote styles.

    Args:
        arg: A quoted Python string literal (e.g. ``"'hello'"``).

    Returns:
        The unquoted string content, or ``arg`` unchanged if it is not a string token.
    """
    s_quote, d_quote = "'''", '"""'
    tokens = get_tokens(arg)
    token = next(tokens)
    while token.type in (tokenize.ENCODING,):
        token = next(tokens)
    s = token.string
    if token.type == tokenize.STRING:
        if s.startswith((s_quote, d_quote)):
            return s[3:-3]
        return s[1:-1]
    return arg


def csvsplit(expr: str) -> list[str]:
    """Split expression on commas while ignoring commas that are contained within quotes
    (including nested quotes)

    """
    result: list[str] = []
    quote_level: list[str] = []
    quote_chars = ('"', "'")
    sep: str = ","

    fp = io.StringIO()
    for char in expr:
        if char in quote_chars:
            # Toggle the quote state if we encounter a quote character
            if quote_level and char == quote_level[-1]:
                quote_level.pop()
            else:
                quote_level.append(char)
            # Add the quote character to the current segment
            fp.write(char)
        elif char == sep and not quote_level:
            # If we encounter a comma and we're not in quotes, finalize the current segment
            result.append(fp.getvalue())
            fp.seek(0)
            fp.truncate()
        else:
            # Add the character to the current segment
            fp.write(char)

    # Add any remaining segment
    if fp.tell():
        result.append(fp.getvalue())

    if quote_level:
        raise ValueError(f"mismatched quotes in {expr!r}")

    return result


def pluralize(word: str, n: int):
    """Return the singular or plural form of ``word`` based on ``n``.

    Applies common English pluralization rules (``-es``, ``-ies``, ``-s``).

    Args:
        word: Singular form of the word.
        n: Count used to determine singular vs. plural.

    Returns:
        Pluralized (or unchanged) word string.
    """
    if n == 1:
        return word
    elif word.endswith(("s", "sh", "ss", "z", "x", "ch")):
        return f"{word}es"
    elif word.endswith("y"):
        return f"{word[:-1]}ies"
    return f"{word}s"


def stringify(arg: Any, float_fmt: str | None = None) -> str:
    """Turn the thing into a string"""
    if hasattr(arg, "string"):
        return arg.string
    if isinstance(arg, float) and float_fmt is not None:
        return float_fmt % arg
    elif isinstance(arg, float):
        return f"{arg:g}"
    elif isinstance(arg, int):
        return f"{arg:d}"
    return str(arg)


def truncate_middle(text: str, max_length: int = 254, sep: str = "...") -> str:
    """Returns truncated string with ``sep`` replacing middle."""
    if max_length < 0:
        raise ValueError("max_length must be >= 0")
    if not sep:
        raise ValueError("sep must be a non-empty string")
    if len(text) <= max_length:
        return text
    if max_length <= len(sep):
        return sep[:max_length]
    keep = max_length - len(sep)
    left = keep // 2
    right = keep - left
    return f"{text[:left]}{sep}{text[-right:]}"


class SimpleTemplate:
    """Minimal ``$var`` / ``${var}`` string template with a custom ``substitute`` method.

    Attributes:
        string: The raw template string.
        pattern: Compiled regex matching ``$name`` and ``${name}`` placeholders.
    """

    def __init__(self, s: str) -> None:
        self.string = s
        self.pattern = re.compile(r"\$(\w+)|\$\{([^}]+)\}")

    def substitute(self, mapping: Mapping[str, str], missing: str | None = None):
        """Replace placeholders using ``mapping``.

        Args:
            mapping: Dictionary of variable substitutions.
            missing: Value to use for unresolved placeholders.  If ``None``,
                unresolved placeholders are left as-is in the output.

        Returns:
            The substituted string.
        """

        def repl(m: re.Match) -> str:
            key = m.group(1) or m.group(2)
            if key in mapping:
                return mapping[key]
            elif missing is None:
                return m.group(0)
            return missing

        return self.pattern.sub(repl, self.string)
