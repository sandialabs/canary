.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-tui:

Interactive explorer (TUI)
==========================

``canary tui`` opens an interactive, full-screen terminal explorer over the
current workspace.  It is a front end to the same application that powers the
command line: everything it shows comes from the workspace database, and every
run it launches goes through the same execution path as :ref:`canary
run<canary-run>`.  You can browse jobs and results, drill into logs, edit a test
and rerun it, cancel a run, and even start a brand-new run -- all without leaving
the screen.

.. note::

   The TUI requires an interactive terminal.  When standard input is not a TTY
   (for example in a pipeline), or when ``--once`` is given, it renders a single
   frame and exits instead of entering the interactive loop.

Launching
---------

Open the explorer over the current workspace:

.. code-block:: console

   canary tui

Discover and run tests on launch, then explore them (the positional paths are
classified exactly as :ref:`canary run<canary-run>` classifies them -- a
directory, a test file, a :ref:`tag<usage-filter>`, or a spec ``ID``):

.. code-block:: console

   canary tui ./tests

If no workspace exists yet, a launch with paths creates one as the run proceeds.

Render a single, non-interactive frame (handy for a quick status snapshot):

.. code-block:: console

   canary tui --once

The layout
----------

The explorer is organized top to bottom:

* a **header** with the workspace path, spec/session counts, and a per-status
  tally;
* an optional **run prompt** (while you are typing a run to start);
* an optional **live-run panel** (while a run is in flight) with a progress bar,
  running/pending counts, per-status tallies, and elapsed time;
* the **job table** -- one scrollable row per job showing name, ``ID``, status,
  phase, and duration; the cursor row is highlighted and marked rows show a
  check;
* an optional **detail pane** for the selected job;
* a **footer** with the active filter, position, and a context-sensitive key
  hint.

The table refreshes automatically (see ``--refresh``) and immediately when a
running job reports progress, so a live run animates in place.

Key bindings
------------

**Navigation**

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Key
     - Action
   * - ``j`` / ``↓``
     - Move down one row
   * - ``k`` / ``↑``
     - Move up one row
   * - ``g`` / ``G``
     - Jump to the first / last row
   * - ``PgUp`` / ``PgDn``
     - Move by a page
   * - ``d``
     - Toggle the detail pane for the selected job
   * - ``f``
     - Cycle the status filter through the statuses present
   * - ``a``
     - Clear the status filter (show all)
   * - ``q`` / ``Esc``
     - Quit (or cancel a run in flight -- see below)

**Logs**

Press ``Enter`` or ``Space`` on a job to open its captured output.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Key
     - Action
   * - ``j`` / ``k``
     - Scroll one line
   * - ``PgUp`` / ``PgDn``
     - Scroll by a page
   * - ``g``
     - Jump to the top (stops following)
   * - ``G``
     - Jump to the bottom and follow new output
   * - ``f``
     - Toggle tail-follow
   * - ``q`` / ``Enter`` / ``Esc``
     - Return to the job table

When you open the log of a job that is part of a run in flight, the view starts
in **follow** mode: it re-reads the job's output as it grows and stays pinned to
the bottom (shown by a ``● live`` marker).  Scrolling up freezes the view so you
can read back; press ``G`` (or ``f``) to resume following.

**Running tests**

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Key
     - Action
   * - ``x``
     - Mark / unmark the current row (and advance)
   * - ``c``
     - Clear all marks
   * - ``r``
     - Rerun the marked jobs, or the cursor row if none are marked
   * - ``e``
     - Edit the selected test's file, then offer to rerun it
   * - ``:``
     - Start a run from scratch (see below)

Reruns and new runs execute **in place**: the explorer stays on screen while the
run proceeds in a separate process and streams progress into the table and the
live-run panel.  You never hand the terminal over to a separate ``canary run``.

.. note::

   ``e`` opens the test file in ``vim``.  The TUI intentionally uses ``vim``
   rather than ``$VISUAL``/``$EDITOR`` so it never launches a windowed editor
   that would detach from the terminal.  After a save that changes the file, the
   edited test is pre-marked so you can rerun it with ``r``.

Starting a run from scratch
---------------------------

Press ``:`` to open the run prompt, type a path, directory, tag, view path, or
spec ``ID``, and press ``Enter``:

.. code-block:: text

   run › ./tests/regression

The input is classified with the same logic as :ref:`canary run<canary-run>`, so
anything you could pass to ``canary run`` works here.  If the input cannot be
classified (for example a path that does not exist), the reason is shown briefly
in the footer and no run is started.  Press ``Esc`` to cancel the prompt.

Cancelling a run
----------------

While a run is in flight, ``q`` / ``Esc`` **cancels the run** instead of quitting
(the footer hint changes to ``q/esc cancel run``).  Cancelling terminates the
run's process; jobs that already finished keep their results, and the explorer
settles from the database so you stay where you were.  Press ``q`` / ``Esc``
again once the run has settled to quit.

Relationship to the command line
---------------------------------

The TUI adds no behavior of its own beyond presentation: it reads results
through the same query surface as :ref:`canary status<basics-status>` and
:ref:`canary log<canary-log>`, and it launches runs through the same path as
:ref:`canary run<canary-run>`.  Anything you do in the explorer is reflected in
the workspace and visible to the ordinary commands, and vice versa.
