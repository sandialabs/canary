.. _extending-report:

User defined reports
====================

``nvtest`` can write output in a number of formats: ``JSON``, ``HTML``, ``Markdown``, among others (see :ref:`nvtest-report` for additional formats).  User defined report formats can be created by subclassing ``nvtest.Reporter`` and defining the ``create`` method.  For example, the following will write a custom plain text report.

.. code-block:: python

    class TxtReporter(nvtest.Reporter):
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

By subclassing ``nvtest.Reporter``, the ``nvtest report txt`` command line interface ``TxtReporter`` will automatically be created:

.. code-block:: console

   $ nvtest report txt -h
   usage: nvtest report json [-h]  ...

   positional arguments:

      create    Create TXT report

   options:
      -h, --help  show this help message and exit

Additionally, the signature to ``TxtReporter.create`` will be parsed and added to the command's help page:

.. code-block:: console

   $ nvtest report txt create -h
   usage: nvtest report txt create [-h] [-o O]

   positional arguments:

      create    Create TXT report

   options:
      -h, --help  show this help message and exit
      -o O        Output file name [default: ./output.txt]
