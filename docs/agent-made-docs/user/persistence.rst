.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-persistence:

Persistence
===========

Canary's persistence system stores test specifications, results, and metadata in a workspace database. This enables result tracking, historical analysis, and efficient re-execution of tests.

Workspace Database
------------------

The workspace database is an SQLite database that stores:

- **Job Specifications**: Test definitions and metadata
- **Results**: Execution outcomes and measurements
- **Selections**: Tagged collections of jobs
- **Dependencies**: Relationships between jobs

Database Structure
------------------

The database contains several key tables:

**specs**: Stores job specifications as JSON

.. code-block:: sql

   CREATE TABLE specs (
     spec_id TEXT PRIMARY KEY,
     data TEXT NOT NULL
   )

**results**: Stores execution results

.. code-block:: sql

   CREATE TABLE results (
     spec_id TEXT,
     spec_name TEXT,
     session TEXT,
     workspace TEXT,
     job_state TEXT,
     status_category TEXT,
     status_outcome TEXT,
     status_reason TEXT,
     status_code INTEGER,
     timekeeper TEXT,
     measurements TEXT,
     PRIMARY KEY (spec_id, session)
   )

**spec_deps**: Stores dependency relationships

.. code-block:: sql

   CREATE TABLE spec_deps (
     spec_id TEXT NOT NULL,
     dep_id TEXT NOT NULL,
     PRIMARY KEY (spec_id, dep_id)
   )

**selections**: Stores tagged job collections

.. code-block:: sql

   CREATE TABLE selections (
     tag TEXT,
     spec_id TEXT,
     PRIMARY KEY (tag, spec_id)
   )

Data Lifecycle
--------------

1. **Collection**: Job specifications discovered and stored
2. **Execution**: Results written during test execution
3. **Query**: Data retrieved for analysis and reporting
4. **Cleanup**: Old sessions and results managed

Storing Job Specifications
--------------------------

Job specifications are stored as JSON in the database:

.. code-block:: python

   # Store specifications
   workspace.database.put_specs([job_spec_1, job_spec_2])

   # Load specifications
   specs = workspace.database.load_specs(["spec_id_1", "spec_id_2"])

Result Storage
--------------

Test results are stored with comprehensive metadata:

.. code-block:: python

   result_data = {
       "id": job.id,
       "spec_name": job.spec.name,
       "session": str(job.workspace.session),
       "state": job.state.phase.value,
       "status": {
           "category": job.status.category.value,
           "outcome": job.status.outcome.name,
           "reason": job.status.reason,
           "code": job.status.code
       },
       "timekeeper": job.timekeeper,
       "measurements": job.measurements
   }

Querying Results
----------------

Retrieve results using various criteria:

.. code-block:: python

   # Get latest results for specific jobs
   results = database.get_results(["job_id_1", "job_id_2"])

   # Get result history for a job
   history = database.get_result_history("job_id_1")

   # Get results with dependencies
   results = database.get_results(["job_id_1"], include_upstreams=True)

Selection Management
--------------------

Selections are tagged collections of jobs:

.. code-block:: python

   # Create a selection
   workspace.database.put_selection("regression", [spec_1, spec_2])

   # Load a selection
   specs = workspace.database.load_specs_by_tagname("regression")

   # List all selections
   tags = workspace.database.tags

Dependency Tracking
-------------------

Dependencies are stored and can be queried:

.. code-block:: python

   # Get dependency graph
   graph = database.get_dependency_graph()

   # Get upstream dependencies
   upstreams = database.get_upstream_ids(["job_id_1"])

   # Get downstream dependents
   downstreams = database.get_downstream_ids(["job_id_1"])

Database Operations
-------------------

Common database operations:

.. code-block:: console

   # View database location
   $ ls .canary/workspace.sqlite3

   # Query database directly
   $ sqlite3 .canary/workspace.sqlite3 "SELECT * FROM specs LIMIT 5;"

Result Listener
---------------

The ``ResultListener`` thread monitors execution and writes results:

.. code-block:: python

   listener = database.listener()
   listener.start()

   # Results are automatically written during execution

   listener.stop_and_join()

Data Integrity
--------------

The database ensures:

- **Atomic Writes**: Transactions prevent partial updates
- **Foreign Keys**: Relationships are maintained
- **Indexes**: Efficient querying of large datasets
- **Migrations**: Schema updates are handled automatically

Database Location
-----------------

The workspace database is located at:

.. code-block:: text

   .canary/workspace.sqlite3

Relative to the workspace root directory.

Database Schema Evolution
-------------------------

Canary handles schema migrations automatically. For example, the migration from ``status_state`` to ``job_state`` is handled transparently.

Best Practices
--------------

- **Regular Backups**: Backup the workspace database periodically
- **Cleanup Old Data**: Remove old sessions to manage database size
- **Use Selections**: Organize jobs with meaningful tags
- **Query Efficiently**: Use indexed queries for large datasets
- **Monitor Database Size**: Large databases can impact performance

Troubleshooting
---------------

**Database Locked**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: database is locked

Solution: Ensure no other Canary processes are running, or use ``--workers=1``.

**Corrupted Database**:

.. code-block:: console

   $ canary status
   Error: database disk image is malformed

Solution: Restore from backup or recreate the workspace.

**Slow Queries**:

.. code-block:: console

   $ canary status
   # Takes a long time to complete

Solution: Optimize queries, add indexes, or clean up old data.

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`workspaces`: Workspace structure and management
- :doc:`results`: Result inspection and analysis
- :doc:`query`: Querying database and lock files
- :doc:`/reference/commands.status`: Status command reference
