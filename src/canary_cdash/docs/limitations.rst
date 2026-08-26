Limitations and Diagnostics
============================

While the canary_cdash extension provides robust integration, there are several limitations and edge cases to be aware of.

Limitations
------------

*   **CDash-Centricity**: The extension is designed for CDash. It cannot be used to report to other dashboards unless they are CDash-compatible.
*   **Network Dependency**: The post and summary commands require a stable network connection to the CDash server.
*   **XML Size**: For extremely large test suites, the generated XML files can become very large. Use the -n CHUNK_SIZE option to split the reports into smaller files to avoid server-side timeouts.
*   **GraphQL Dependency**: The summary and make-gitlab-issues commands rely on the CDash GraphQL API. If the server is running an older version of CDash without GraphQL support, these commands will fail.

Diagnostics
------------

*   **Upload Failures**: When the post command fails, the extension logs the error response from the CDash server. Check the logs for Failed to upload... messages.
*   **XML Validation**: If CDash rejects an upload, you can inspect the generated XML files in the session's reports directory (default: /_reports/cdash) and validate them against the XSD schemas found in src/canary_cdash/validators/.
*   **Build Identification**: If results are appearing in the wrong build on CDash, verify that the combination of **Project**, **Site**, **Build Name**, and **Build Stamp** is unique and correct.
