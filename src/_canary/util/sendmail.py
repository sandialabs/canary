# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pwd
import smtplib
import socket
import traceback
from email.mime.text import MIMEText
from getpass import getuser
from io import StringIO

smtp_email_hosts = ["mailgate.sandia.gov", "mailgate2.sandia.gov"]


def sendmail(sendaddr, recvaddrs, subject, content, *, subtype="plain", user=None):
    """Send an email to addresses in recvaddrs

    Args:
      sendaddr: The sending address. If None, it will be set to the user name of this
        process is user @ the current machine.
      recvaddrs: Either a single email address (string), or list of email addresses.
      subtype: subtype sent to MIMEText. Use "html" for sending content that
        contains html (but do not include <html><body> at the beginning and
        </body></html> at the end).
      user: If sendaddr is None, user is the user name used in the sendaddr. If
        None, user will be determined

    Raises:
      SendMailError: if email could not be sent

    """
    user = user or getuser()
    sendaddr = sendaddr or get_sender_address(user=user)
    message = create_message(content, subtype)
    message["Subject"] = subject

    message["From"] = sendaddr
    name = pwd.getpwnam(user).pw_gecos
    FROM = f"{name} <{sendaddr}>"

    if isinstance(recvaddrs, str):
        recvaddrs = [recvaddrs]
    message["To"] = ", ".join(recvaddrs)
    TO = list(recvaddrs)

    # NOTE: Adding 'localhost' here can work, but if the receiver email is
    # unknown, then the mail can appear to succeed but just get dropped.
    # Whereas when using the mailgate hosts, an error will be generated.
    email_hosts = smtp_email_hosts + ["localhost"]
    for host in email_hosts:
        try:
            server = smtplib.SMTP(host)
            server.sendmail(FROM, TO, message.as_string())
            server.quit()
        except:  # noqa: E722
            sio = StringIO()
            traceback.print_exc(50, sio)
            error = sio.getvalue() + "\n"
        else:
            break
    else:
        raise SendMailError(recvaddrs, error)


def create_message(content, subtype):
    if subtype == "html" and "<html>" not in content:
        body = f"""\
<html>
<body>
{content}
</body>
</html>"""
    else:
        body = content
    return MIMEText(body, subtype)


def get_sender_address(*, user=None):
    user = user or getuser()
    if user is None:  # pragma: no cover
        raise Exception("could not determine user name of this process")
    machine = socket.getfqdn()
    return f"{user}@{machine}"


class SendMailError(Exception):
    def __init__(self, recvaddrs, error):
        message = StringIO()
        message.write(
            "Received the following error when attempting to send email to {0}:\n{1}".format(
                ",".join(recvaddrs), error
            )
        )
        super(SendMailError, self).__init__(message.getvalue())

    pass
