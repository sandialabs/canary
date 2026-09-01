Environment and Working Directory
=================================

Canary ensures that CTest tests are executed in the correct environment.

Working Directory
-----------------

The execution directory is determined by the CTest WORKING_DIRECTORY property. If not specified, Canary defaults to the directory containing the CTestTestfile.cmake file. The command is wrapped in a shell that performs a cd into this directory before executing the test command.

Environment Variables
----------------------

**Direct Environment**:
The ENVIRONMENT property is mapped directly to the job's environment variables.

**Environment Modification**:
The ENVIRONMENT_MODIFICATION property allows for more complex changes. Canary supports the following operations:
*   set: Sets the variable to a specific value.
*   unset: Removes the variable from the environment.
*   string_append / string_prepend: Appends or prepends a string to the current value.
*   path_list_append / path_list_prepend: Appends or prepends a value using the colon (:) separator.
*   cmake_list_append / cmake_list_prepend: Appends or prepends a value using the semicolon (;) separator.

Example
-------

A CTest property like ENVIRONMENT_MODIFICATION "PATH=path_list_append:/opt/bin" will result in the value of PATH being updated to /usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-path:/home/agentuser/.local/bin:/projects/.codex/tmp/arg0/codex-arg0W5nfKV:/usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-path:/home/agentuser/.local/bin:/opt/conda/bin:/usr/local/bin:/opt/conda/bin:/usr/local/bin:/opt/conda/bin:/usr/local/bin:/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/bin.
