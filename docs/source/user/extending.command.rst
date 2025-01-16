.. _extending-command:

User defined commands
=====================

Custom commands can be created by subclassing :class:`~_canary.command.Command`.  For example, the following will create a custom command that emails a plain text test report:

.. code-block:: python

    import io

    class Email(canary.Command):

        @property
        def description(self):
            return "Send an email report"

        def setup_parser(self, parser):
            parser.add_argument("--to", required=True)
            parser.add_argument("--from", dest="_from", required=True)

        def execute(self, args) -> int:
            session = canary.Session(".", mode="r")

            fp = io.StringIO()
            for case in self.session.cases:
                if case.mask:
                    continue
                fp.write("====\n")
                fp.write(f"Name: {case.name}\n")
                fp.write(f"Start: {case.start}\n")
                fp.write(f"Finish: {case.finish}\n")
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
