CDash Summaries
===============

The canary_cdash extension can pull data back from a CDash server to generate a standalone HTML summary of the build status across multiple sites.

The summary Command
----------------------

This command queries the CDash API (and GraphQL endpoint) to aggregate results.

.. code-block:: console

   python3 -m canary report cdash summary --project MyProject --url https://cdash.example.org -o summary.html

Options
-------

*   **--project PROJECT**: The CDash project to summarize.
*   **--url URL**: The base CDash URL.
*   **-t TRACK**: Filter by specific CDash build groups (e.g., Nightly, Experimental). Defaults to all.
*   **-m MAILTO**: Email addresses to send the resulting summary to.
*   **-s SKIP_SITE**: A Python regular expression used to exclude specific sites from the summary.
*   **-o OUTPUT**: The filename to write the HTML summary to. If omitted, it prints to stdout.

How it Works
------------

The summary tool:
1.  Queries the CDash index to find builds in the requested groups.
2.  Retrieves failure counts and timing data.
3.  Categorizes failures into **Diffed**, **Timeout**, and **Failed** based on the "details" field provided by the CDash server.
4.  Renders an HTML table with color-coded cells (red for errors, orange for warnings/diffs, limegreen for passes).
