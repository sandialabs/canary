.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Metadata
========

CDash metadata collection and usage in ``canary_cdash`` reports.

Automatically Collected Metadata
---------------------------------

The CDash reporter automatically collects system and build metadata:

+----------------------------+--------------------------------------------------+
| Metadata Field             | Source                                           |
+============================+==================================================+
| ``BuildName``              | ``--build`` command option                       |
+----------------------------+--------------------------------------------------+
| ``SiteName``               | ``--site`` option or system hostname             |
+----------------------------+--------------------------------------------------+
| ``BuildStamp``             | Auto-generated or ``--build-stamp`` option       |
+----------------------------+--------------------------------------------------+
| ``Generator``              | ``canary version X.Y.Z``                         |
+----------------------------+--------------------------------------------------+
| ``Hostname``               | System hostname                                  |
+----------------------------+--------------------------------------------------+
| ``OSName``                 | Canary system configuration                      |
+----------------------------+--------------------------------------------------+
| ``OSRelease``              | Canary system configuration                      |
+----------------------------+--------------------------------------------------+
| ``OSVersion``              | Canary system configuration                      |
+----------------------------+--------------------------------------------------+
| ``OSPlatform``             | Canary system configuration                      |
+----------------------------+--------------------------------------------------+
| ``CompilerName``           | CMake configuration (if available)               |
+----------------------------+--------------------------------------------------+
| ``CompilerVersion``        | CMake configuration (if available)               |
+----------------------------+--------------------------------------------------+

Build Stamp Format
------------------

Automatic build stamp format:

.. code-block:: text

   %Y%m%d-%H%M-<track>

Example: ``20240101-1200-Experimental``

Components:

- ``%Y%m%d``: Year, month, day (e.g., ``20240101``)
- ``%H%M``: Hour, minute (e.g., ``1200``)
- ``<track>``: Build track (e.g., ``Experimental``)

Custom Build Stamp
~~~~~~~~~~~~~~~~~~

Provide custom build stamp with ``--build-stamp``:

.. code-block:: console

   $ python3 -m canary report cdash create \
       --build MyBuild \
       --build-stamp 20240101-1200-Nightly

Custom build stamps must follow the same format.

Metadata in XML
---------------

Metadata is written to the ``Site`` element in CDash XML:

.. code-block:: xml

   <Site>
     <BuildName>MyBuild</BuildName>
     <SiteName>MySite</SiteName>
     <BuildStamp>20240101-1200-Experimental</BuildStamp>
     <Generator>canary version 1.0.0</Generator>
     <Hostname>myserver.example.com</Hostname>
     <OSName>Linux</OSName>
     <OSRelease>5.15.0</OSRelease>
     <OSVersion>#41-Ubuntu SMP</OSVersion>
     <OSPlatform>x86_64</OSPlatform>
     <CompilerName>GNU</CompilerName>
     <CompilerVersion>11.3.0</CompilerVersion>
   </Site>

Metadata Sources
----------------

Canary Configuration
~~~~~~~~~~~~~~~~~~~~

Metadata is primarily sourced from Canary's configuration system:

.. code-block:: python

   # System metadata
   canary.config.get("system:os:release")      # OS release
   canary.config.get("system:platform")        # Platform
   canary.config.get("system:os:fullversion")  # Full OS version
   canary.config.get("system:arch")            # Architecture

   # CMake metadata (if available)
   canary.config.get("cmake:compiler:vendor")   # Compiler vendor
   canary.config.get("cmake:compiler:version")  # Compiler version

Command-Line Overrides
~~~~~~~~~~~~~~~~~~~~~~

Command-line options override automatic metadata:

+----------------------------+--------------------------------------------------+
| Option                     | Overrides                                        |
+============================+==================================================+
| ``--build``                | ``BuildName``                                    |
+----------------------------+--------------------------------------------------+
| ``--site``                 | ``SiteName``                                     |
+----------------------------+--------------------------------------------------+
| ``--track``                | Build stamp track                                |
+----------------------------+--------------------------------------------------+
| ``--build-stamp``          | Complete ``BuildStamp``                          |
+----------------------------+--------------------------------------------------+

Metadata Validation
-------------------

The CDash reporter validates metadata:

- **Build Name**: Must be non-empty string
- **Site Name**: Must be non-empty string
- **Build Stamp**: Must match format ``%Y%m%d-%H%M-<track>``
- **Generator**: Must be non-empty string

Invalid metadata results in errors during XML generation.

Metadata and Build Identification
----------------------------------

CDash uses this metadata to identify builds:

- **Project**: CDash project name (specified during upload)
- **Site**: Site name
- **Build Name**: Build configuration name
- **Build Stamp**: Unique timestamp for the build

Together, these uniquely identify a build in CDash.

Best Practices
--------------

1. **Unique Build Names**: Use descriptive build names
2. **Consistent Site Names**: Use consistent site naming
3. **Meaningful Tracks**: Use tracks like ``Experimental``, ``Nightly``, ``Release``
4. **Validate Metadata**: Check metadata before upload
5. **Document Conventions**: Document metadata conventions for your project

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`xml-generation` - XML generation
- :doc:`uploading` - Upload process
