import datetime
import io
from getpass import getuser

import nvtest
from _nvtest.util import logging
from _nvtest.util.sendmail import sendmail


@nvtest.plugin.register(scope="main", stage="setup")
def setup_parser(parser: nvtest.Parser) -> None:
    user = getuser()
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


@nvtest.plugin.register(scope="session", stage="after_run")
def send_email_summary(session: nvtest.Session) -> None:
    mail_to = nvtest.config.getoption("mail_to")
    if mail_to is None:
        return
    sendaddr = nvtest.config.getoption("mail_from")
    if sendaddr is None:
        raise RuntimeError("missing required argument --mail-from")
    recvaddrs = [_.strip() for _ in mail_to.split(",") if _.split()]
    html_report = generate_html_report(session)
    date = datetime.datetime.fromtimestamp(session.start)
    st_time = date.strftime("%m/%d/%Y")
    subject = f"NVTest Summary for {st_time}"
    logging.info(f"Sending summary to {', '.join(recvaddrs)}")
    sendmail(sendaddr, recvaddrs, subject, html_report, subtype="html")


def generate_html_report(session: nvtest.Session) -> str:
    totals: dict[str, list[nvtest.TestCase]] = {}
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
    file.write("<body>\n<h1>NVTest test summary</h1>\n<table>\n")
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
