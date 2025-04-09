# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import io
from typing import TYPE_CHECKING

from ... import config
from ...config.argparsing import Parser
from ...util import logging
from ...util.sendmail import sendmail
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...session import Session
    from ...test.case import TestCase


@hookimpl
def canary_addoption(parser: Parser) -> None:
    parser.add_argument(
        "--mail-to",
        help="Send a test session summary to the comma separated list of email addresses",
        command="run",
    )
    parser.add_argument(
        "--mail-from",
        help="Send mail from this user",
        command="run",
    )


@hookimpl
def canary_session_post_finalize(session: "Session") -> None:
    mail_to = config.getoption("mail_to")
    if mail_to is None:
        return
    sendaddr = config.getoption("mail_from")
    if sendaddr is None:
        raise RuntimeError("missing required argument --mail-from")
    recvaddrs = [_.strip() for _ in mail_to.split(",") if _.split()]
    html_report = generate_html_report(session)
    date = datetime.datetime.fromtimestamp(session.start)
    st_time = date.strftime("%m/%d/%Y")
    subject = f"Canary Summary for {st_time}"
    logging.info(f"Sending summary to {', '.join(recvaddrs)}")
    sendmail(sendaddr, recvaddrs, subject, html_report, subtype="html")


def generate_html_report(session: "Session") -> str:
    totals: dict[str, list["TestCase"]] = {}
    for case in session.active_cases():
        group = case.status.name.title()
        totals.setdefault(group, []).append(case)
    file = io.StringIO()
    file.write("<html><head><style>\n")
    file.write("table{font-family:arial,sans-serif;border-collapse:collapse;}\n")
    file.write("td, th {border: 1px solid #dddddd; text-align: left; ")
    file.write("padding: 8px; width: 100%}\n")
    file.write("tr:nth-child(even) {background-color: #dddddd;}\n")
    file.write("</style>")
    file.write("<body>\n<h1>Canary test summary</h1>\n<table>\n")
    file.write("<tr><th>Test</th><th>Duration</th><th>Status</th></tr>\n")
    for group, cases in totals.items():
        for case in sorted(cases, key=lambda c: c.duration):
            file.write(
                f"<tr><td>{case.display_name}</td>"
                f"<td>{case.duration:.2f}</td>"
                f"<td>{case.status.html_name}</td></tr>\n"
            )
    file.write("</table>\n</body>\n</html>")
    return file.getvalue()
