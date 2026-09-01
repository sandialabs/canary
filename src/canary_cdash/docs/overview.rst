Overview
========

The canary_cdash extension provides integration between Canary and CDash, a dashboard for visualizing test results and regressions.

This extension is a **reporting plugin**. It consumes completed Canary results from a session and transforms them into the XML format required by CDash. It does not define how tests are authored or how they are executed; its sole responsibility is the translation and delivery of results.

Main Features
-------------

*   **XML Generation**: Converts Canary jobs, statuses, timings, and outputs into CDash-compatible XML.
*   **Subproject Support**: Maps Canary labels to CDash subprojects to organize results.
*   **Automated Upload**: Posts generated XML files to a CDash server via HTTP.
*   **Dashboard Summaries**: Generates standalone HTML summaries by aggregating data from CDash via the GraphQL API.
*   **GitLab Integration**: Synchronizes CDash failures with GitLab issues, creating and updating issues based on failing tests.

Basic Workflow
--------------

Reporting to CDash typically involves two steps:

1. **Generate XML**: Use the create command to transform Canary session results into XML files.

   .. code-block:: console

      python3 -m canary report cdash create --site myhost --build mybuild

2. **Post to CDash**: Use the post command to upload those files to the CDash server.

   .. code-block:: console

      python3 -m canary report cdash post --project MyProject --url https://cdash.example.org CDASH/Test-0.xml

Note
----

CDash is an external service. Uploading results requires network access and a correctly configured CDash project.
