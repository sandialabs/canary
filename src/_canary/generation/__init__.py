# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary generation pipeline stage.

The "discover -> generate -> resolve" front of the Canary pipeline:

* :mod:`~_canary.generation.generator` -- the public
  :class:`~_canary.generation.generator.AbstractSpecGenerator` base a plugin
  subclasses to turn a source file into unresolved spec IR.
* :mod:`~_canary.generation.collect` -- the :class:`Collector` that walks scan
  paths and matches files to generators.
* :mod:`~_canary.generation.generate` -- the :class:`Generator` orchestration
  that expands generators into specs and resolves their dependencies.

The public ``canary.AbstractSpecGenerator``/``canary.Generator``/
``canary.Collector`` are re-exported from here.
"""
