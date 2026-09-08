.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CDash Summaries
===============

Generate HTML summaries of CDash dashboards.

Command Reference
-----------------

.. code-block:: console

   $ python3 -m canary report cdash summary -h

Options:

+------------------------------------+--------------------------------------------------+
| Option                             | Description                                      |
+====================================+==================================================+
| ``--project CDASH_PROJECT``        | CDash project name                               |
+------------------------------------+--------------------------------------------------+
| ``--url CDASH_URL``                | Base CDash URL                                   |
+------------------------------------+--------------------------------------------------+
| ``-t TRACK``                       | Filter by build group (repeatable)               |
+------------------------------------+--------------------------------------------------+
| ``-m MAILTO``                      | Email address to send summary (repeatable)       |
+------------------------------------+--------------------------------------------------+
| ``-s SKIP_SITE``                   | Skip site (regex pattern, repeatable)            |
+------------------------------------+--------------------------------------------------+
| ``-o OUTPUT``                      | Filename to write HTML summary [default: stdout] |
+------------------------------------+--------------------------------------------------+

Basic Usage
-----------

Generate summary for today:

.. code-block:: console

   $ python3 -m canary report cdash summary \
       --project MyProject \
       --url https://cdash.example.org

Generate summary for specific date:

.. code-block:: console

   $ python3 -m canary report cdash summary \
       --project MyProject \
       --url https://cdash.example.org \
       --date 2024-01-01

Filter by Groups
~~~~~~~~~~~~~~~~

.. code-block:: console

   $ python3 -m canary report cdash summary \
       --project MyProject \
       --url https://cdash.example.org \
       -t Nightly -t Experimental

Skip Specific Sites
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ python3 -m canary report cdash summary \
       --project MyProject \
       --url https://cdash.example.org \
       -s "test-.*" -s "backup-.*"

Summary Features
----------------

The CDash summary provides:

- **Build Overview**: Summary of all builds
- **Test Results**: Pass/fail statistics
- **Failure Analysis**: Detailed failure information
- **Trend Analysis**: Historical trends
- **Site Comparison**: Compare results across sites

Summary Output
--------------

HTML summary is written to standard output or can be redirected:

.. code-block:: console

   $ python3 -m canary report cdash summary \
       --project MyProject \
       --url https://cdash.example.org > summary.html

Summary Requirements
--------------------

- **CDash Access**: Requires read access to CDash project
- **Network**: Requires internet access to CDash server
- **Authentication**: CDash server must allow summary access

Summary Limitations
-------------------

- **Data Availability**: Limited to data available in CDash
- **Performance**: Large projects may generate large summaries
- **Customization**: Limited customization options
- **Real-time**: Summary reflects CDash data at time of generation

Summary Best Practices
----------------------

1. **Regular Generation**: Generate summaries regularly
2. **Date Ranges**: Use appropriate date ranges
3. **Filtering**: Use filters to focus on relevant data
4. **Automation**: Automate summary generation
5. **Archiving**: Archive summaries for historical reference

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`uploading` - Upload functionality