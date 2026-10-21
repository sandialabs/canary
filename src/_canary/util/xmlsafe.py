# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Helpers for producing well-formed XML from arbitrary test output.

Test names, commands, failure reasons and captured output may contain bytes
that are not allowed in XML 1.0 (NUL, BEL, ESC and other C0 controls, lone
surrogates, U+FFFE/U+FFFF) or the sequence ``]]>``, which terminates a CDATA
section.  Writing such text verbatim either crashes ``xml.dom.minidom``
(``]]>`` in CDATA) or yields a document that every consumer (CDash, GitLab,
Jenkins) rejects.  Route all untrusted text through these helpers.
"""

import re
import xml.dom.minidom as xdom

#: ANSI CSI / OSC escape sequences (colors, cursor movement, hyperlinks).
_ANSI = re.compile(
    r"""
    \x1b\[[0-?]*[ -/]*[@-~]          # CSI ... final byte
    | \x1b\][^\x07\x1b]*(?:\x07|\x1b\\)  # OSC ... BEL or ST
    | \x1b[@-Z\\-_]                  # other 2-byte escapes
    """,
    re.VERBOSE,
)

#: Characters that are not allowed anywhere in an XML 1.0 document.
_INVALID_XML = re.compile("[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")

#: Default cap (characters) for large text blobs such as captured test output.
DEFAULT_MAX_TEXT = 1_000_000


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI.sub("", text)


def xml_safe(text: object, *, max_length: int | None = None, ansi: bool = True) -> str:
    """Return *text* with every character that is invalid in XML 1.0 removed.

    Invalid characters are replaced with ``U+FFFD`` (so their presence remains
    visible), ANSI escape sequences are stripped when *ansi* is true, and the
    result is truncated (keeping the head and tail) to *max_length* characters.
    """
    s = "" if text is None else str(text)
    if ansi:
        s = strip_ansi(s)
    s = _INVALID_XML.sub("\ufffd", s)
    if max_length is not None and max_length > 0 and len(s) > max_length:
        keep = max(0, max_length - 64)
        head, tail = s[: keep // 2], s[len(s) - keep // 2 :]
        s = f"{head}\n\n... [{len(s) - 2 * (keep // 2)} characters truncated] ...\n\n{tail}"
    return s


def cdata_nodes(document: xdom.Document | None, text: object, **kwargs) -> list[xdom.CDATASection]:
    """Return CDATA section node(s) holding *text* safely.

    ``]]>`` cannot appear inside a CDATA section, so the text is split at each
    occurrence into consecutive sections (``]]`` + ``>``), which XML parsers
    concatenate back into the original text.
    """
    s = xml_safe(text, **kwargs)
    # "a]]>b" -> CDATA("a]]") + CDATA(">b"): no section contains "]]>".
    pieces = s.split("]]>")
    chunks = [pieces[0]]
    for piece in pieces[1:]:
        chunks[-1] += "]]"
        chunks.append(">" + piece)
    nodes: list[xdom.CDATASection] = []
    for chunk in chunks:
        node = xdom.CDATASection()
        node.data = chunk
        node.ownerDocument = document  # type: ignore[assignment]
        nodes.append(node)
    return nodes


def text_node(document: xdom.Document | None, text: object, **kwargs) -> xdom.Text:
    """Return an (escaped-on-write) text node holding *text* with invalid characters removed."""
    node = xdom.Text()
    node.data = xml_safe(text, **kwargs)
    node.ownerDocument = document  # type: ignore[assignment]
    return node


def set_attribute(element: xdom.Element, name: str, value: object) -> None:
    """``element.setAttribute`` with invalid XML characters removed from *value*."""
    element.setAttribute(name, xml_safe(value))
