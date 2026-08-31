.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-reporters:

Reporters
=========

Reporters generate custom output formats from Canary's execution data. Reporter extensions enable integration with external systems and specialized analysis tools.

Reporter Extension Model
-------------------------

Implement ``CanaryReporter`` to create custom reporters:

.. code-block:: python

   from canary import CanaryReporter

   class MyReporter(CanaryReporter):
       type = "myformat"
       description = "Custom report format"

       def create(self, output=None):
           # Generate report
           result = generate_report()
           if output:
               with open(output, "w") as f:
                   f.write(result)
           else:
               print(result)

Reporter Registration
---------------------

Register reporters using ``canary_session_reporter`` hook:

.. code-block:: python

   @canary.hookimpl
   def canary_session_reporter():
       return MyReporter()

Built-in Reporters
------------------

Canary includes several built-in reporters:

- **JSON**: Structured JSON output
- **JUnit**: JUnit XML format
- **HTML**: Web-based reports
- **Text**: Simple text format
- **Markdown**: Markdown reports

Custom Report Creation
----------------------

Create reporters with custom formats:

.. code-block:: python

   class CSVReporter(CanaryReporter):
       type = "csv"
       description = "CSV report format"

       def create(self, output=None):
           workspace = canary.Workspace.load()
           jobs = workspace.load_jobs()

           # Generate CSV
           csv_data = generate_csv(jobs)

           if output:
               with open(output, "w") as f:
                   f.write(csv_data)
           else:
               print(csv_data)

Session and Job Data Access
----------------------------

Access execution data in reporters:

.. code-block:: python

   def create(self, output=None):
       workspace = canary.Workspace.load()
       session = workspace.load_session("latest")
       jobs = workspace.load_jobs()

       # Process job data
       for job in jobs:
           name = job.spec.name
           status = job.status
           duration = job.timekeeper.duration()
           measurements = job.measurements

Artifacts and Measurements
--------------------------

Access test artifacts and measurements:

.. code-block:: python

   def create(self, output=None):
       workspace = canary.Workspace.load()
       jobs = workspace.load_jobs()

       for job in jobs:
           # Access artifacts
           artifacts = job.artifacts

           # Access measurements
           metrics = job.measurements
           custom_metric = metrics.get("custom_metric", 0)

CDash/GitLab Integration
------------------------

Create reporters for CI systems:

.. code-block:: python

   class CDashReporter(CanaryReporter):
       type = "cdash"
       description = "CDash upload format"

       def create(self, output=None):
           workspace = canary.Workspace.load()
           jobs = workspace.load_jobs()

           # Generate CDash XML
           cdash_xml = generate_cdash_xml(jobs)

           if output:
               with open(output, "w") as f:
                   f.write(cdash_xml)
           else:
               upload_to_cdash(cdash_xml)

Reporter Best Practices
-----------------------

**Output Format**:

- Use standard formats where possible
- Document custom format specifications
- Provide format validation

**Error Handling**:

- Validate output paths
- Handle file permissions
- Provide meaningful error messages

**Performance**:

- Stream large outputs
- Minimize memory usage
- Optimize data processing

Reporter Examples
-----------------

**JSON Reporter**:

.. code-block:: python

   import json
   import canary

   class JSONReporter(CanaryReporter):
       type = "json"
       description = "JSON report format"

       def create(self, output=None):
           workspace = canary.Workspace.load()
           jobs = workspace.load_jobs()

           data = {
               "session": "latest",
               "jobs": [{
                   "name": job.spec.name,
                   "status": job.status.category.value,
                   "duration": job.timekeeper.duration(),
                   "measurements": job.measurements
               } for job in jobs]
           }

           result = json.dumps(data, indent=2)

           if output:
               with open(output, "w") as f:
                   f.write(result)
           else:
               print(result)

**HTML Reporter**:

.. code-block:: python

   import canary

   class HTMLReporter(CanaryReporter):
       type = "html"
       description = "HTML report format"

       def create(self, output=None):
           workspace = canary.Workspace.load()
           jobs = workspace.load_jobs()

           html = generate_html_report(jobs)

           if output:
               with open(output, "w") as f:
                   f.write(html)
           else:
               print(html)

Reporter Integration
--------------------

**Command Integration**:

.. code-block:: console

   $ canary report myformat -h
   $ canary report myformat create -o report.myformat

**Configuration Integration**:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--report-format", choices=["myformat", "csv", "json"])

Reporter Troubleshooting
------------------------

**Reporter Not Found**:

- Verify ``canary_session_reporter`` hook registration
- Check reporter type uniqueness
- Ensure plugin is loaded

**Output Issues**:

- Validate output paths
- Check file permissions
- Test with different formats

**Data Access Problems**:

- Verify workspace state
- Check session availability
- Validate job data

See Also
--------

- :doc:`plugins`: Reporter plugin registration
- :doc:`hooks`: Reporter-related hooks
- :doc:`../user/results`: Result data structure
- :doc:`/reference/commands.report`: Report command