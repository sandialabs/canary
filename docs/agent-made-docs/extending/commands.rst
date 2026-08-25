.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-commands:

Commands
========

Canary's command system allows extensions to add new subcommands to the CLI. Commands integrate seamlessly with Canary's argument parsing and execution model.

CanarySubcommand
----------------

The base class for all commands is ``CanarySubcommand``:

.. code-block:: python

   from canary import CanarySubcommand

   class MyCommand(CanarySubcommand):
       name = "my-command"
       description = "My custom command"

       def setup_parser(self, parser):
           parser.add_argument("--option", help="Custom option")

       def execute(self, args):
           print(f"Running with option: {args.option}")
           return 0

Command Registration
--------------------

Register commands using the ``canary_addcommand`` hook:

.. code-block:: python

   @canary.hookimpl
   def canary_addcommand(parser):
       parser.add_command(MyCommand())

Parser Setup
------------

Configure command-line arguments in ``setup_parser``:

.. code-block:: python

   def setup_parser(self, parser):
       # Positional arguments
       parser.add_argument("input", help="Input file")

       # Optional arguments
       parser.add_argument("--output", "-o", help="Output file")

       # Flags
       parser.add_argument("--verbose", "-v", action="store_true")

       # Choices
       parser.add_argument("--format", choices=["json", "yaml", "text"])

Command Execution
-----------------

Implement command logic in ``execute``:

.. code-block:: python

   def execute(self, args):
       # Access arguments
       input_file = args.input
       output_file = args.output
       verbose = args.verbose

       # Implement command logic
       result = process_files(input_file, output_file, verbose)

       # Return exit code
       return 0 if result else 1

Argument Parser Conventions
---------------------------

**Argument Names**: Use descriptive, consistent names

.. code-block:: python

   parser.add_argument("--input-file", dest="input_file")

**Help Text**: Provide clear, concise help

.. code-block:: python

   parser.add_argument("--timeout", help="Timeout in seconds (default: 30)")

**Default Values**: Set sensible defaults

.. code-block:: python

   parser.add_argument("--workers", type=int, default=4)

**Type Conversion**: Use appropriate types

.. code-block:: python

   parser.add_argument("--port", type=int)
   parser.add_argument("--debug", action="store_true")

Command Best Practices
----------------------

**Argument Design**:

- Use consistent naming conventions
- Group related arguments
- Provide sensible defaults
- Validate inputs early

**Error Handling**:

- Validate arguments before execution
- Provide meaningful error messages
- Use appropriate exit codes

**Help Text**:

- Write clear, concise descriptions
- Include examples where helpful
- Document argument interactions

**Testing**:

- Test with various argument combinations
- Verify error handling
- Check help output formatting

Command Examples
----------------

**Simple Reporting Command**:

.. code-block:: python

   import canary

   class ReportCommand(canary.CanarySubcommand):
       name = "report"
       description = "Generate custom reports"

       def setup_parser(self, parser):
           parser.add_argument("--format", choices=["json", "html", "text"],
                              default="text", help="Output format")
           parser.add_argument("--output", "-o", help="Output file")
           parser.add_argument("session", nargs="?", default="latest",
                              help="Session to report on")

       def execute(self, args):
           workspace = canary.Workspace.load()
           session = workspace.load_session(args.session)

           if args.format == "json":
               data = generate_json_report(session)
           elif args.format == "html":
               data = generate_html_report(session)
           else:
               data = generate_text_report(session)

           if args.output:
               with open(args.output, "w") as f:
                   f.write(data)
           else:
               print(data)

           return 0

**Job Analysis Command**:

.. code-block:: python

   import canary

   class AnalyzeCommand(canary.CanarySubcommand):
       name = "analyze"
       description = "Analyze job execution patterns"

       def setup_parser(self, parser):
           parser.add_argument("--slow", type=int, help="Show slowest N jobs")
           parser.add_argument("--failed", action="store_true",
                              help="Show only failed jobs")
           parser.add_argument("--metrics", action="store_true",
                              help="Show performance metrics")

       def execute(self, args):
           workspace = canary.Workspace.load()
           jobs = workspace.load_jobs()

           if args.failed:
               jobs = [j for j in jobs if j.status.is_failure()]

           if args.slow:
               jobs.sort(key=lambda j: j.duration, reverse=True)
               jobs = jobs[:args.slow]

           if args.metrics:
               print(generate_metrics_report(jobs))
           else:
               print(generate_summary_report(jobs))

           return 0

Command Integration
-------------------

**Workspace Access**:

.. code-block:: python

   workspace = canary.Workspace.load()
   session = workspace.load_session("latest")
   jobs = workspace.load_jobs()

**Configuration Access**:

.. code-block:: python

   debug_mode = canary.config.getoption("debug")
   timeout = canary.config.getoption("timeout")

**Resource Management**:

.. code-block:: python

   pool = canary.resource_manager.get_pool()
   available = pool.slots_available("cpus")

Command Troubleshooting
-----------------------

**Command Not Found**:

- Verify ``canary_addcommand`` hook registration
- Check command name spelling
- Ensure plugin is loaded

**Argument Parsing Errors**:

- Validate argument definitions
- Check for conflicting arguments
- Test with ``--help`` flag

**Execution Failures**:

- Validate input arguments
- Check workspace state
- Verify resource availability

Avoiding Command Conflicts
--------------------------

**Unique Names**: Choose distinctive command names

.. code-block:: python

   name = "my-custom-command"  # Good
   name = "run"               # Bad (conflicts with built-in)

**Namespace Arguments**: Use unique argument names

.. code-block:: python

   parser.add_argument("--my-option", help="Custom option")
   # Avoid: --workers (conflicts with built-in)

**Help Text**: Clearly distinguish custom commands

.. code-block:: python

   description = "Custom analysis tool (extension)"

See Also
--------

- :doc:`plugins`: Plugin registration for commands
- :doc:`hooks`: Command-related hooks
- :doc:`../user/running`: Execution concepts
- :doc:`../reference/commands`: Built-in commands