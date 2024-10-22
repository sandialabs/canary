.. _developers-style:

Python style guide
==================

Python code should adhere to `PEP 8 <https://peps.python.org/pep-0008/>`_, with the following clarifications:

* Use four spaces for indentation, no tabs.
* Use Unix-style line endings (LF, aka ``\\n`` character).
* Spaces around operators (except for keyword arguments).
* Use ``CamelCase`` for classes and exception types. Use ``underscore_case`` for everything else.

Automated formatting
--------------------

Python code should be automatically formatted and checked using ``ruff format`` and ``ruff check --fix``, respectively.  Merge request pipelines check code with both ``ruff format`` and ``ruff check`` to test for compliance.

Type hints
----------

All new code should include `type hints <https://docs.python.org/3/library/typing.html>`_ and be checked with ``mypy``.  Merge request pipelines check code with ``mypy`` to test for compliance.

Exceptions to PEP 8
-------------------

Line width:
  Maximum width for lines is 99 (enforced by ``ruff``)

Docstrings
----------

Docstrings should be written using the `Google docstring style <https://google.github.io/styleguide/pyguide.html>`_.  NumPy style docstrings are not supported.
