.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-configuration:

Configuration
=============

Canary's configuration system manages settings across multiple sources with clear precedence rules. Configuration controls all aspects of Canary's behavior, from resource allocation to workspace management.

Configuration Sources and Precedence
------------------------------------

Canary loads configuration from multiple sources in order of increasing precedence:

1. **System Defaults**: Built-in default values
2. **Site Configuration**: System-wide settings (``/etc/canary/config.yaml``)
3. **Global Configuration**: User-specific settings (``~/.config/canary/config.yaml``)
4. **Local Configuration**: Workspace-specific settings (``.canary/config.yaml``)
5. **Environment Variables**: ``CANARYCFGFILE`` or ``CANARYCFG64``
6. **Command Line**: ``-c`` and ``-e`` options

Later sources override earlier ones, allowing progressive customization.

Global Configuration
--------------------

Global configuration is stored in:

- **Linux/macOS**: ``~/.config/canary/config.yaml``
- **Windows**: ``%APPDATA%\canary\config.yaml``

Example global configuration:

.. code-block:: yaml

   canary:
     debug: false
     log_level: INFO
     plugins:
       - canary_hpc
     workspace:
       view:
         name: TestResults
         mode: symlink
         when: always

Local/Workspace Configuration
-----------------------------

Local configuration is stored in ``.canary/config.yaml`` within the workspace directory. This allows workspace-specific customization.

Example local configuration:

.. code-block:: yaml

   canary:
     run:
       timeout:
         default: 600.0
         long: 1800.0
     workspace:
       view:
         mode: copy
         only: failed

Command-Line Configuration
--------------------------

Override configuration using ``-c`` for YAML paths:

.. code-block:: console

   $ canary -c config:debug:true -c config:log_level:DEBUG run .

Set environment variables using ``-e``:

.. code-block:: console

   $ canary -e CUDA_VISIBLE_DEVICES=0,1 -e OMP_NUM_THREADS=4 run .

Configuration Commands
----------------------

**Show Configuration**:

.. code-block:: console

   $ canary config show
   canary:
     debug: false
     log_level: INFO
     plugins: []
     workspace:
       view:
         name: TestResults
         mode: symlink
         when: always

Show specific sections:

.. code-block:: console

   $ canary config show timeout
   canary:
     timeout:
       session: -1.0
       multiplier: 1.0
       fast: 120.0
       default: 300.0
       long: 900.0

**Set Configuration**:

.. code-block:: console

   $ canary config set --local timeout:default 600.0
   $ canary config set --global plugins "[canary_hpc]"

Configuration Sections
----------------------

**Debug and Logging**:

.. code-block:: yaml

   canary:
     debug: true
     log_level: DEBUG

**Plugins**:

.. code-block:: yaml

   canary:
     plugins:
       - canary_hpc
       - canary_cdash

**Workspace Views**:

.. code-block:: yaml

   canary:
     workspace:
       view:
         name: TestResults
         mode: symlink
         when: always
         only: all

**Timeout Configuration**:

.. code-block:: yaml

   canary:
     run:
       timeout:
         session: -1.0
         multiplier: 1.0
         fast: 120.0
         default: 300.0
         long: 900.0

**Environment Management**:

.. code-block:: yaml

   canary:
     environment:
       prepend-path:
         PATH: /opt/canary/bin
       append-path:
         PYTHONPATH: /opt/canary/lib
       set:
         OMP_NUM_THREADS: 4
       unset:
         - VARIABLE_TO_REMOVE

Plugin-Added Options
--------------------

Plugins can extend configuration with custom sections. For example, the HPC extension might add:

.. code-block:: yaml

   canary:
     hpc:
       scheduler: slurm
       partition: gpu
       account: project123

Timeout Configuration
---------------------

Timeouts control execution duration limits:

- **session**: Overall session timeout (-1.0 = unlimited)
- **multiplier**: Global timeout multiplier
- **fast**: Short test timeout
- **default**: Standard test timeout
- **long**: Extended test timeout

Example:

.. code-block:: yaml

   canary:
     run:
       timeout:
         default: 600.0
         long: 1800.0

Workspace View Configuration
----------------------------

Views control result presentation:

- **name**: View directory name
- **mode**: ``symlink``, ``copy``, or ``hardlink``
- **when**: ``always``, ``never``, or ``on_failure``
- **only**: ``all``, ``failed``, or ``passed``

Example:

.. code-block:: yaml

   canary:
     workspace:
       view:
         name: TestResults
         mode: symlink
         when: always
         only: all

Configuration Aliases
---------------------

Canary supports configuration aliases for common options:

- ``-d`` or ``--debug``: Sets ``config:debug:true``
- ``-v`` or ``--verbose``: Sets ``config:log_level:DEBUG``

Environment Modification
------------------------

Canary can modify the execution environment:

.. code-block:: yaml

   canary:
     environment:
       prepend-path:
         PATH: /custom/bin
         LD_LIBRARY_PATH: /custom/lib
       set:
         CUSTOM_VAR: value
       unset:
         - UNWANTED_VAR

Configuration Best Practices
----------------------------

**Layered Configuration**:

- Use global config for user preferences
- Use local config for workspace-specific settings
- Use command line for one-off overrides

**Version Control**:

- Commit ``.canary/config.yaml`` to version control
- Document configuration requirements

**Environment Isolation**:

- Use environment variables for sensitive data
- Avoid hardcoding paths in configuration

**Timeout Strategy**:

- Set reasonable defaults
- Use ``long`` timeout for resource-intensive tests
- Use ``fast`` timeout for quick validation tests

Configuration Pitfalls
----------------------

**Overriding Too Much**:

- Avoid overriding core settings unnecessarily
- Prefer local overrides to global changes

**Hardcoded Paths**:

- Use relative paths or environment variables
- Avoid absolute paths in configuration

**Complex Environment Modifications**:

- Test environment changes thoroughly
- Document environment requirements

**Ignoring Precedence**:

- Remember that command line overrides all other sources
- Use ``canary config show`` to verify effective configuration

Configuration Examples
----------------------

**Developer Workstation**:

.. code-block:: yaml

   canary:
     debug: true
     log_level: DEBUG
     workspace:
       view:
         mode: symlink
         only: all
     run:
       timeout:
         default: 300.0

**CI Environment**:

.. code-block:: yaml

   canary:
     debug: false
     log_level: INFO
     workspace:
       view:
         mode: copy
         only: failed
     run:
       timeout:
         default: 600.0
         long: 1800.0

**HPC Cluster**:

.. code-block:: yaml

   canary:
     plugins:
       - canary_hpc
     workspace:
       view:
         mode: hardlink
         only: all
     run:
       timeout:
         default: 1800.0
         long: 7200.0

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`workspaces`: Workspace structure and management
- :doc:`running`: Execution configuration
- :doc:`/reference/commands.config`: Config command reference
