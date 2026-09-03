.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-json:

JSON report
===========

A JSON report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "ellipsis": 0, "cwd": "examples"}, {"args": "canary report json create", "cwd": "examples"}, {"args": "cat canary.json", "cwd": "examples"}]

Schema
------

The output is a single JSON file (``canary.json`` by default) containing a flat object keyed by
job ID.  Each value is a serialized job record:

.. code-block:: json

   {
     "<job_id>": {
       "spec": {
         "id":          "<sha256-hex>",
         "family":      "<string>",
         "file_root":   "<path>",
         "file_path":   "<path>",
         "keywords":    ["<string>", "..."],
         "parameters":  {"<name>": "<value>"},
         "attributes":  {"<name>": "<value>"},
         "timeout":     0.0,
         "command":     ["<string>", "..."]
       },
       "status": {
         "category":    {"value": "PASS|FAIL|CANCEL|SKIP|NONE"},
         "outcome":     {"value": "<int>"},
         "reason":      "<string or null>",
         "code":        0
       },
       "timekeeper": {
         "_submitted":  0.0,
         "_staged":     0.0,
         "_started":    0.0,
         "_stopped":    0.0,
         "_finished":   0.0
       },
       "measurements": {"data": {"<name>": "<value>"}},
       "workspace":    {"root": "<path>", "path": "<path>", "session": "<string>"},
       "variables":    {"<name>": "<value>"},
       "dependencies": [{"<dep>": "..."}],
       "allocation":   {"metadata": {}, "resources": {}, "state": {}},
       "rparameters":  {"cpus": 1, "gpus": 0, "nodes": 1}
     }
   }

All ``timekeeper`` timestamps are Unix epoch floats; ``-1.0`` means that phase was not reached.
``status.outcome`` integer values: ``0``=success, ``64``=diffed, ``65``=failed, ``68``=timeout,
``70``=cancelled, ``80``=skipped, ``81``=blocked.

