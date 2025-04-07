.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-command:

User defined commands
=====================

User defined commands are created by returning a :class:`~_canary.plugins.types.CanarySubcommand` from the :func:`~_canary.plugins.hookspec.canary_subcommand` plugin hook. For example, the following will create a custom command that emails a plain text test report:

.. code-block:: python

    import io
    import canary

    @canary.hookimpl
    def canary_subcommand():
        return Email()


    class Email(canary.CanarySubcommand):
        name = "email"
        description = "Send an email report"

        def setup_parser(self, parser):
            parser.add_argument("--to", required=True)
            parser.add_argument("--from", dest="_from", required=True)

        def email(self, args) -> None:
            session = canary.Session(".", mode="r")
            fp = io.StringIO()
            for case in self.session.active_cases():
                fp.write("====\n")
                fp.write(f"Name: {case.name}\n")
                fp.write(f"Start: {case.start}\n")
                fp.write(f"Finish: {case.stop}\n")
                fp.write(f"Status: {case.status.value}\n")
            send_email(to=args.to, recipients=[args._from], body=fp.getvalue())


On the command line, you will now see:

.. code-block:: console

   $ canary -h
   usage: canary ...

   canary - an application testing framework

   subcommands:

      ...
      email    Send an email report
      ...

and

.. code-block:: console

   $ canary email -h
   usage: canary email [-h] --to TO --from FROM

   options:

      -h, --help  show this help message and exit
      --to     TO
      --from   FROM
