.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

XML Generation
==============

The ``canary_cdash`` extension generates CDash-compatible XML files from Canary workspace results.

Command Reference
-----------------

.. code-block:: console

   $ python3 -m canary report cdash create -h

Options:

+------------------------------------+---------------------------------------------------------+
| Option                             | Description                                             |
+====================================+=========================================================+
| ``--build name``                   | Build name for CDash [required]                         |
+------------------------------------+---------------------------------------------------------+
| ``--site name``                    | Site name for CDash [default: hostname]                 |
+------------------------------------+---------------------------------------------------------+
| ``--track track``                  | Build track [default: Experimental]                     |
+------------------------------------+---------------------------------------------------------+
| ``--build-stamp stamp``            | Custom build stamp (format: ``%Y%m%d-%H%M-<track>``)    |
+------------------------------------+---------------------------------------------------------+
| ``--name-format {short,long}``     | Name format [default: short]                            |
+------------------------------------+---------------------------------------------------------+
| ``-f file``                        | Read from existing XML file                             |
+------------------------------------+---------------------------------------------------------+
| ``-d directory``                   | Output directory [default: ``$session/_reports/cdash``] |
+------------------------------------+---------------------------------------------------------+
| ``-n CHUNK_SIZE``                  | Chunk size (-1 for no chunking) [default: 500]          |
+------------------------------------+---------------------------------------------------------+
| ``-L LABEL``                       | Treat label as subproject                               |
+------------------------------------+---------------------------------------------------------+
| ``--subproject-labels LABELS``     | Comma-separated subproject labels                       |
+------------------------------------+---------------------------------------------------------+

Basic Usage
-----------

Generate CDash XML from current workspace:

.. code-block:: console

   $ python3 -m canary report cdash create --build MyBuild --site MySite

Generate with custom track:

.. code-block:: console

   $ python3 -m canary report cdash create --build MyBuild --track Nightly

Generate with custom build stamp:

.. code-block:: console

   $ python3 -m canary report cdash create --build MyBuild --build-stamp 20240101-1200-Experimental

Chunking
--------

Large test suites are automatically split into chunks:

.. code-block:: console

   $ python3 -m canary report cdash create --build MyBuild -n 200

This creates multiple XML files with 200 tests each.

Disable chunking with ``-n -1``:

.. code-block:: console

   $ python3 -m canary report cdash create --build MyBuild -n -1

Output Directory
----------------

Default output directory: ``$session/_reports/cdash``

Custom output directory:

.. code-block:: console

   $ python3 -m canary report cdash create --build MyBuild -d /custom/output

Build Stamp Generation
----------------------

Automatic build stamp format: ``%Y%m%d-%H%M-<track>``

Example: ``20240101-1200-Experimental``

Custom build stamp must follow the same format.

Metadata Collection
-------------------

Automatically collected metadata:

+----------------------------+--------------------------------------------------+
| Metadata                   | Source                                           |
+============================+==================================================+
| Hostname                   | System hostname                                  |
+----------------------------+--------------------------------------------------+
| OS Name                    | Canary configuration                             |
+----------------------------+--------------------------------------------------+
| OS Release                 | Canary configuration                             |
+----------------------------+--------------------------------------------------+
| OS Version                 | Canary configuration                             |
+----------------------------+--------------------------------------------------+
| OS Platform                | Canary configuration                             |
+----------------------------+--------------------------------------------------+
| Compiler Name              | CMake configuration (if available)               |
+----------------------------+--------------------------------------------------+
| Compiler Version           | CMake configuration (if available)               |
+----------------------------+--------------------------------------------------+

Status Mapping
--------------

Canary job status to CDash test status mapping:

+----------------------------+--------------------------------------------------+
| Canary Status              | CDash Status                                     |
+============================+==================================================+
| ``SUCCESS``                | ``passed``                                       |
+----------------------------+--------------------------------------------------+
| ``FAILED``                 | ``failed``                                       |
+----------------------------+--------------------------------------------------+
| ``SKIPPED``                | ``notrun``                                       |
+----------------------------+--------------------------------------------------+
| ``TIMEOUT``                | ``failed`` (with timeout reason)                 |
+----------------------------+--------------------------------------------------+
| ``CANCELLED``              | ``notrun``                                       |
+----------------------------+--------------------------------------------------+

Test Information
----------------

Each CDash test includes:

- **Test Name**: Based on job family and parameters
- **Command**: Job command line
- **Status**: Mapped from Canary status
- **Time**: Job execution time
- **Output**: Captured job output (compressed if large)
- **Labels**: Job keywords and custom labels
- **Subproject**: Assigned via labels or hooks
- **Artifacts**: Attached files
- **Measurements**: Timings and custom measurements

Example XML Structure
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: xml

   <Site>
     <BuildName>MyBuild</BuildName>
     <SiteName>MySite</SiteName>
     <BuildStamp>20240101-1200-Experimental</BuildStamp>
     <Generator>canary version X.Y.Z</Generator>
     <!-- Metadata -->
   </Site>

   <Testing>
     <Test>
       <Name>test_name</Name>
       <Path>path/to/test</Path>
       <FullName>full.test.name</FullName>
       <FullCommandLine>command args</FullCommandLine>
       <Results>
         <NamedMeasurement type="text/string" name="status">passed</NamedMeasurement>
         <NamedMeasurement type="text/string" name="completion_status">Completed</NamedMeasurement>
         <NamedMeasurement type="numeric/double" name="Execution Time">1.23</NamedMeasurement>
       </Results>
       <Labels>
         <Label>label1</Label>
         <Label>label2</Label>
       </Labels>
     </Test>
   </Testing>

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`reporter-plugin` - Plugin hooks
- :doc:`customization` - Customization examples
