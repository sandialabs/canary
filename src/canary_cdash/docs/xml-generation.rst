XML Generation
===============

The canary_cdash extension translates Canary's internal session state into CDash XML files.

How it Works
------------

When canary report cdash create is run, the extension iterates over the jobs in the current session. Each job is mapped to a CDash <Test> element.

Status Mapping
--------------

Canary maps job statuses to CDash statuses and completion categories as follows:

.. list-table::
   :widths: 30 30 30
   :header-rows: 1

   * - Canary Status
     - CDash Status
     - Completion Status
   * - success
     - passed
     - Completed
   * - timeout
     - failed
     - Timeout
   * - failure
     - failed
     - Completed
   * - cancelled
     - failed
     - Completed
   * - skipped
     - notdone
     - notrun
   * - Not Done
     - notdone
     - notrun

For failures, the Fail Reason measurement in the XML is populated using the job's status reason or a default string based on the failure outcome.

Build Metadata
--------------

To uniquely identify a build in CDash, the following metadata is collected:

*   **Project**: Specified during the post command.
*   **Site**: The machine name. Defaults to the current system hostname (os.uname().nodename) unless --site is provided.
*   **Build Name**: The name of the configuration/build, provided via --build.
*   **Build Stamp**: A timestamp uniquely identifying the run. Canary generates this automatically in the format %Y%m%d-%H%M-track (where track defaults to Experimental) unless --build-stamp is provided.
*   **Generator**: Defaults to canary version <version>.

Command Options
---------------

*   **--name-format {short,long}**: Controls how the test name appears in the XML. short uses the job's display name; long uses the full path relative to the session root.
*   **-n CHUNK_SIZE**: Splits results into multiple XML files of $ entries each. Use -1 for a single file. The default is 500.
*   **-L LABEL**: Treats a specific Canary label as a CDash subproject.
*   **--subproject-labels LABELS**: A comma-separated list of labels to be treated as subprojects.

Artifacts and Measurements
--------------------------

*   **Measurements**: All job measurements are converted to CDash <NamedMeasurement> elements. Strings are typically text/string, while numbers are numeric/double.
*   **Output**: The job's stdout/stderr is embedded as a base64-encoded, gzip-compressed measurement.
*   **Artifacts**: If any files are identified as artifacts via the canary_cdash_artifacts hook, they are bundled into a tar.gz archive and attached to the test.
