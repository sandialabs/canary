.. _extending-report:

User defined reports
====================

``canary`` can write output in a number of formats: ``JSON``, ``HTML``, ``Markdown``, among others (see :ref:`canary-report` for additional formats).  User defined report formats can be created by subclassing ``canary.Reporter`` and defining the ``create`` method.  For example, the following will write a custom plain text report.

.. code-block:: python

    class TxtReporter(canary.Reporter):
        def create(self, o: str = "./output.txt") -> None:
            """Create a plain text output

            Args:
              dest: Output file name

            """
            with open(dest, "w") as fh:
                for case in self.session.cases:
                    if case.mask:
                        continue
                    fh.write("====\n")
                    fh.write(f"Name: {case.name}\n")
                    fh.write(f"Start: {case.start}\n")
                    fh.write(f"Finish: {case.finish}\n")
                    fh.write(f"Status: {case.status.value}\n")

By subclassing ``canary.Reporter``, the ``canary report txt`` command line interface ``TxtReporter`` will automatically be created:

.. code-block:: console

   $ canary report txt -h
   usage: canary report txt [-h]  ...

   positional arguments:

      create    Create TXT report

   options:
      -h, --help  show this help message and exit

Additionally, the signature to ``TxtReporter.create`` will be parsed and added to the command's help page:

.. code-block:: console

   $ canary report txt create -h
   usage: canary report txt create [-h] [-o O]

   positional arguments:

      create    Create TXT report

   options:
      -h, --help  show this help message and exit
      -o O        Output file name [default: ./output.txt]
