# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import tokenize
from typing import Generator


def get_tokens(path) -> Generator[tokenize.TokenInfo, None, None]:
    return tokenize.tokenize(io.BytesIO(path.encode("utf-8")).readline)


def strip_quotes(arg: str) -> str:
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
