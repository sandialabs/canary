.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary-vvtest:

VVTest test scripts
===================

``canary`` can discover, interpret, and execute tests written in the ``vvtest`` format. This makes
it possible to run existing vvtest suites under ``canary`` while using ``canary`` features such as
filtering, reporting, and (when applicable) scheduled/HPC execution.

Directives
----------

``vvtest`` directives are ``#VVT:`` comment lines that appear before any executable code in a
``.vvt`` file.  Scanning stops at the first non-comment code token, so directives placed after
``import`` statements or other code lines are silently ignored.

Line syntax::

    #VVT: directive_name (option1, option2=value, ...) : arguments
    #VVT::  continuation of previous line's arguments

All directives accept the following **filtering options** in the ``(...)`` clause, which gate the
directive to matching test variants:

* ``testname="<expr>"`` — apply only when the test name matches the expression
* ``options="<expr>"`` — apply only when run with matching ``-o`` options
* ``platforms="<expr>"`` — apply only when the platform matches (supports ``not``, ``or``)
* ``parameters="<expr>"`` — apply only when parameter values match

Supported directives
~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Directive
     - Description
   * - ``keywords``
     - ``#VVT: keywords : kw1 kw2 ...`` — attach keywords for filtering
   * - ``copy``
     - ``#VVT: copy : file1 file2 ...`` or ``#VVT: copy (rename) : src1,dst1 src2,dst2`` — copy
       files into the test working directory; the ``rename`` option enables ``src,dst`` pairs
   * - ``link``
     - ``#VVT: link : file1 ...`` or ``#VVT: link (rename) : src1,dst1`` — symlink files into
       the test working directory
   * - ``sources``
     - ``#VVT: sources : file1 file2`` — declare source files without staging them
   * - ``parameterize``
     - ``#VVT: parameterize (OPTIONS) : name1,name2 = val1,val2  val3,val4 ...`` — generate
       parameterized variants; OPTIONS: ``autotype``, ``int``, ``float``, ``str``, ``generator``.
       The special names ``np``, ``ndevice``, and ``nnode`` are always cast to ``int`` and map to
       ``canary``'s ``cpus``, ``gpus``, and ``nodes`` resource meta-parameters respectively.
   * - ``analyze``
     - ``#VVT: analyze : --flag`` or ``#VVT: analyze : script.py`` — declare an aggregate/analysis
       job; an argument starting with ``-`` is treated as a flag, otherwise as a script path
   * - ``timeout``
     - ``#VVT: timeout : 5m`` / ``1h 30m`` / ``HH:MM:SS`` — set per-test timeout
   * - ``skipif``
     - ``#VVT: skipif (reason="...") : <python-expr>`` — skip if expression is truthy;
       ``os``, ``sys``, and ``importable()`` are in scope
   * - ``baseline``
     - ``#VVT: baseline : src,dst`` or ``#VVT: baseline : --flag`` — declare rebaseline behavior
   * - ``enable``
     - ``#VVT: enable : true|false`` — enable or disable a test variant; bare ``enable`` = ``true``
   * - ``name`` / ``testname``
     - ``#VVT: name : my_name`` — create an additional named test family from the same file
   * - ``depends_on``
     - ``#VVT: depends on (expect=N, result="pass") : pattern`` — dependency on a glob pattern;
       ``result`` accepts ``pass``, ``diff``, ``fail``, ``skip`` (translated to ``canary`` status
       vocabulary at parse time)
   * - ``include``
     - ``#VVT: include : path/to/directives.txt`` — pull in directives from an external file;
       supports all filter options; recursive
   * - ``filter_warnings``
     - ``#VVT: filter_warnings : <python-expr>`` — suppress scan-time warnings if truthy
   * - ``preload``
     - ``#VVT: preload : source-script path/to/env.sh`` — accepted but has no execution effect in
       ``canary`` (see :ref:`differences` below)

.. _differences:

Differences from native vvtest
-------------------------------

The following behavioural differences apply when running ``.vvt`` tests under ``canary``:

* **``preload`` is a no-op.** The directive is accepted without error but has no effect.  Use
  ``canary.directives.source()`` or ``canary.directives.load_module()`` from a ``.pyt`` wrapper
  if environment setup is needed.

* **``DEPDIRMAP`` is always empty.** ``canary`` always writes ``vvtest_util.DEPDIRMAP = {}``.
  Tests that rely on ``DEPDIRMAP`` will fail silently; use ``DEPDIRS`` instead.

* **``analyze`` requires at least one ``parameterize``.** If ``#VVT: analyze`` is declared but
  no ``parameterize`` directive is present, ``canary`` raises an error.  Native vvtest allows
  analyze-only tests without parameters.

* **Stdout is redirected to ``execute.log``.** All ``.vvt`` jobs capture stdout and stderr to
  ``execute.log`` (rather than ``canary-out.txt`` used by ``.pyt`` jobs).

* **CDash test name format differs.** ``canary`` generates CDash test names as
  ``family[param1=val1,param2=val2]`` (bracket notation) rather than vvtest's dot-separated style.

* **Directive scanning stops at the first code token.** Directives placed after any ``import``
  statement or other code line are silently ignored.  Native vvtest scans the whole file.

