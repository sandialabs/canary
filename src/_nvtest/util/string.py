import io
import re
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


def ilist(arg: str) -> list[int]:
    """Convert comma separated list of integers in `arg` into a list of int

    List can also contain ranges.

    Examples:

    >>> ilist("1,2,3")
    [1, 2, 3]
    >>> ilist("1,2,3,5-9")
    [1, 2, 3, 5, 6, 7, 8, 9]

    """
    arg_wo_space = re.sub(r"[ \t]", "", arg)
    if re.search(r"^\d+$", arg_wo_space):
        return [int(arg_wo_space)]
    if re.search(r"^\d+(,\d+)*$", arg_wo_space):
        return [int(_) for _ in arg_wo_space.split(",") if _.split()]
    if re.search(r"^(\d+(-\d_)?)(,\d+(-\d+)?)*$", arg_wo_space):
        ints: list[int] = []
        for x in arg_wo_space.split(","):
            if "-" in x:
                a, b = [int(_) for _ in x.split("-") if _.split()]
                ints.extend(range(a, b + 1))
            else:
                ints.append(int(x))
        return ints
    raise ValueError(f"{arg!r}: unknown integer list representation")
