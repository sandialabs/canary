.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Workspaces
==========

A **workspace** is the central execution environment for Canary. It manages job specifications, execution results, sessions, and views in a structured directory format.

What a Workspace Is
-------------------

The Canary workspace is a directory (``.canary`` by default) that contains:

- Job specifications and their metadata
- Execution results and historical data
- Session information and runtime state
- Result views for easy navigation
- Configuration and database files
- Temporary files and caches

The workspace provides isolation, persistence, and organization for all Canary operations within a project or directory tree.

Workspace Structure
-------------------

A typical Canary workspace has the following structure:

.. code-block:: text

   .canary/
   ├── WORKSPACE.TAG          # Workspace anchor file
   ├── VERSION                # Workspace version
   ├── config.yaml            # Workspace configuration
   ├── workspace.sqlite3      # Main database
   ├── refs/                  # Session references
   │   └── latest             # -> ../sessions/{session_name}
   ├── sessions/              # Execution sessions
   │   └── {session_name}/    # Individual session directories
   │       ├── session.lock    # Session manifest
   │       └── {job_dirs}/    # Job execution directories
   ├── cache/                 # Cached data and views
   │   ├── jobs/               # Job timing cache
   │   └── view                # Latest view reference
   ├── tmp/                   # Temporary files
   ├── logs/                  # Log files
   └── reports/               # Generated reports

WORKSPACE.TAG
-------------

The ``WORKSPACE.TAG`` file serves as the workspace anchor. It:

- Marks a directory as a Canary workspace
- Contains workspace metadata and creation timestamp
- Enables workspace discovery when traversing directory trees
- Prevents accidental workspace creation in nested directories

This file should not be edited manually.

VERSION
-------

The ``VERSION`` file contains the workspace format version (e.g., ``1.0.0``). It:

- Tracks the workspace schema version
- Enables backward compatibility handling
- Indicates when migrations may be needed
- Helps diagnose version mismatch issues

This file should not be edited manually.

config.yaml
-----------

The ``config.yaml`` file stores workspace-specific configuration:

.. code-block:: yaml

   canary:
     # Workspace-specific settings
     # Overrides default Canary configuration
     # Applied when workspace is loaded

This file can be edited to customize workspace behavior, but changes should be made carefully and documented.

workspace.sqlite3
-----------------

The SQLite database stores all persistent Canary data:

- **specs table**: Job specifications (JobSpec objects)
- **results table**: Execution results and status
- **selections table**: Tagged job selections
- **selection_meta table**: Selection metadata
- **spec_deps table**: Dependency relationships
- **specs_meta table**: Source file and view mappings

The database uses efficient indexing for fast queries and supports concurrent access during execution.

refs/ Directory
---------------

The ``refs/`` directory contains symbolic references to sessions:

- **latest**: Points to the most recent session directory
  - Format: relative path to session (e.g., ``../sessions/2024-01-15T12-34-56.789012``)
  - Updated automatically after each session
  - Used by default when no specific session is requested

Additional reference files can be created for specific workflows or automation.

sessions/ Directory
-------------------

The ``sessions/`` directory contains execution session data:

- Each subdirectory represents one execution session
- Session names are typically ISO-format timestamps (e.g., ``2024-01-15T12-34-56.789012``)
- Can contain custom-named sessions for specific purposes

Session Directory Contents:

- **session.lock**: Session manifest with metadata
- **{job_dirs}/**: Individual job execution directories
- **testcase.lock**: Job state and results (in each job directory)

session.lock
~~~~~~~~~~~~

The ``session.lock`` file contains session metadata:

.. code-block:: json

   {
     "name": "2024-01-15T12-34-56.789012",
     "prefix": ".canary/sessions/2024-01-15T12-34-56.789012",
     "job_ids": ["job_id_1", "job_id_2", "..."],
     "returncode": 0,
     "started_on": "2024-01-15T12:34:56.789012",
     "finished_on": "2024-01-15T12:35:12.345678",
     "argv": ["canary", "run", "."],
     "config": { "..." },
     "measurements": { "..." }
   }

This file should not be edited manually.

cache/ Directory
----------------

The ``cache/`` directory stores performance data and view references:

- **jobs/**: Job timing cache for adaptive scheduling
  - Organized by ID prefix (e.g., ``jobs/ab/cdef...``)
  - Contains historical timing statistics
  - Used for runtime estimation and load balancing

- **view**: Reference to the latest results view
  - JSON file pointing to the current TestResults location
  - Enables quick access to latest results

cache/jobs/ Structure
~~~~~~~~~~~~~~~~~~~~~

Job cache files store timing history for adaptive scheduling:

.. code-block:: json

   {
     "cache": {
       ".version": [3, 0],
       "meta": {
         "name": "job_display_name",
         "id": "job_id",
         "root": "/path/to/workspace",
         "path": "relative/path/to/test.pyt"
       },
       "history": {
         "SUCCESS": 5,
         "FAILED": 2,
         "last_run": "Mon Jan 15 12:34:56 2024"
       },
       "metrics": {
         "time": {
           "count": 5,
           "mean": 2.345,
           "min": 1.234,
           "max": 4.567,
           "variance": 0.123
         }
       }
     }
   }

This data is used for:

- Predicting job runtime for scheduling
- Balancing workload across resources
- Detecting performance regressions
- Optimizing execution order

tmp/ Directory
--------------

The ``tmp/`` directory contains temporary files:

- Database transaction files and locks
- Inter-process communication queues
- Temporary result spools
- Intermediate files during execution

This directory is automatically cleaned and should not be modified manually.

logs/ Directory
---------------

The ``logs/`` directory contains Canary log files:

- Execution logs from Canary itself
- Debug and diagnostic information
- Plugin and extension logs
- Historical logs from previous operations

Log files use consistent naming with timestamps for easy correlation with sessions.

reports/ Directory
------------------

The ``reports/`` directory contains generated reports:

- Execution summaries in various formats
- HTML, JSON, XML, or custom report outputs
- Integration reports (CDash, etc.)
- Custom analysis and visualization outputs

This directory is populated by reporter plugins during and after execution.

Results Views
-------------

Canary creates **views** to provide easy access to results:

- **TestResults/**: Symlink/hardlink tree mirroring source structure
- Contains latest successful results for each job
- Organized by source path for intuitive navigation
- Updated automatically after each session

View Structure:

.. code-block:: text

   TestResults/
   ├── path/
   │   └── to/
   │       └── test_case[a=1,b=2]/  # Symlink to session job directory
   │           ├── canary-out.txt    # stdout
   │           ├── testcase.lock     # Job state
   │           └── artifacts/        # Output files
   └── another/
       └── test.pyt/                # Another job
           └── ...

Workspace Creation
------------------

Workspaces are created using ``Workspace.create()``:

.. code-block:: python

   from _canary.workspace import Workspace

   # Create workspace in current directory
   ws = Workspace.create(path=".")

   # Create workspace with custom path
   ws = Workspace.create(path="/path/to/project")

   # Force recreation if existing
   ws = Workspace.create(path=".", force=True)

This creates the complete directory structure and initializes the database.

Workspace Loading
-----------------

Workspaces are loaded using ``Workspace.load()``:

.. code-block:: python

   from _canary.workspace import Workspace

   # Load workspace from current directory
   ws = Workspace.load()

   # Load workspace from specific path
   ws = Workspace.load("/path/to/project")

   # Load workspace from parent directories
   ws = Workspace.load("subdirectory/in/workspace")

Canary searches upward from the starting path to find the workspace anchor.

Workspace Removal
-----------------

Workspaces can be removed using ``Workspace.remove()``:

.. code-block:: python

   from _canary.workspace import Workspace

   # Remove workspace from current directory
   Workspace.remove()

   # Remove workspace from specific path
   Workspace.remove("/path/to/project")

This removes both the ``.canary`` directory and the associated ``TestResults`` view.

What Users Should and Should Not Edit
-------------------------------------

**Safe to edit (with care):**

- ``config.yaml``: Workspace configuration
- ``TestResults/``: Result view (though typically managed automatically)
- Custom reports in ``reports/``

**Do not edit manually:**

- ``WORKSPACE.TAG``: Workspace anchor
- ``VERSION``: Workspace version
- ``workspace.sqlite3``: Database (use Canary commands)
- ``refs/latest``: Session reference
- ``session.lock``: Session manifests
- ``testcase.lock``: Job state files
- ``cache/``: Performance cache
- ``tmp/``: Temporary files

Editing these files manually can corrupt the workspace and lead to inconsistent state.

Workspace Best Practices
------------------------

1. **One workspace per project**: Create workspaces at project roots
2. **Version control**: Include ``.canary/`` in version control for reproducibility
3. **Configuration management**: Use ``config.yaml`` for project-specific settings
4. **Regular cleanup**: Use ``canary gc`` to clean old sessions
5. **Backup important data**: Database contains valuable historical results
6. **Avoid manual editing**: Use Canary commands for workspace operations
7. **Document customization**: Note any workspace-specific configuration changes

Workspace Lifecycle
-------------------

1. **Creation**: ``Workspace.create()`` or ``canary init``
2. **Configuration**: Edit ``config.yaml`` as needed
3. **Job discovery**: ``ws.collect()`` or ``canary collect``
4. **Selection**: ``ws.select()`` or ``canary select``
5. **Execution**: ``ws.run()`` or ``canary run``
6. **Query**: ``ws.db`` operations or ``canary status``
7. **Reporting**: Reporter plugins or ``canary report``
8. **Cleanup**: ``canary gc`` or ``Workspace.remove()``

This lifecycle ensures consistent workspace state throughout Canary operations.
