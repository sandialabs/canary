# -*- coding: utf-8 -*-
# Copyright (c) 2010, 2011, 2012, Sebastian Wiesner <lunaryorn@gmail.com>
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
sphinxcontrib.programoutput
===========================

This extension provides a directive to include the output of commands as
literal block while building the docs.

.. moduleauthor::  Sebastian Wiesner  <lunaryorn@gmail.com>
"""

import hashlib
import io
import json
import os
import shlex
import sys
import tempfile
from collections import defaultdict
from collections import namedtuple
from subprocess import STDOUT
from subprocess import Popen

from docutils import nodes
from docutils.parsers import rst
from docutils.parsers.rst.directives import flag
from docutils.parsers.rst.directives import nonnegative_int
from docutils.parsers.rst.directives import unchanged
from docutils.statemachine import StringList
from sphinx.util import logging as sphinx_logging

__version__ = "0.17"

logger = sphinx_logging.getLogger("contrib.programoutput")


class program_output(nodes.Element):
    pass


g_fp = g_path = None


def _container_wrapper(directive, literal_node, caption):
    container_node = nodes.container("", literal_block=True, classes=["literal-block-wrapper"])
    parsed = nodes.Element()
    directive.state.nested_parse(StringList([caption], source=""), directive.content_offset, parsed)
    if isinstance(parsed[0], nodes.system_message):  # pragma: no cover
        # TODO: Figure out if this is really possible and how to produce
        # it in a test case.
        msg = "Invalid caption: %s" % parsed[0].astext()
        raise ValueError(msg)
    assert isinstance(parsed[0], nodes.Element)
    caption_node = nodes.caption(parsed[0].rawsource, "", *parsed[0].children)
    caption_node.source = literal_node.source
    caption_node.line = literal_node.line
    container_node += caption_node
    container_node += literal_node
    return container_node


def _slice(value):
    parts = [int(v.strip()) for v in value.split(",")]
    if len(parts) > 2:
        raise ValueError("too many slice parts")
    return tuple((parts + [None] * 2)[:2])


class ProgramOutputDirective(rst.Directive):
    has_content = False
    final_argument_whitespace = True
    required_arguments = 1

    option_spec = dict(
        shell=flag,
        prompt=flag,
        nostderr=flag,
        nocache=flag,
        silent=flag,
        anyreturncode=flag,
        ellipsis=_slice,
        setup=unchanged,
        extraargs=unchanged,
        returncode=nonnegative_int,
        cwd=unchanged,
        caption=unchanged,
        name=unchanged,
    )

    def run(self):
        env = self.state.document.settings.env

        node = program_output()
        node.line = self.lineno
        node["command"] = self.arguments[0]

        if self.name == "command-output":
            node["show_prompt"] = True
        else:
            node["show_prompt"] = "prompt" in self.options

        node["silent"] = "silent" in self.options
        node["nocache"] = "nocache" in self.options
        node["anyreturncode"] = "anyreturncode" in self.options

        node["hide_standard_error"] = "nostderr" in self.options
        node["extraargs"] = self.options.get("extraargs", "")
        node["setup"] = self.options.get("setup", None)
        _, cwd = env.relfn2path(self.options.get("cwd", "/"))
        node["working_directory"] = cwd
        node["use_shell"] = "shell" in self.options
        node["returncode"] = self.options.get("returncode", 0)
        if "ellipsis" in self.options:
            node["strip_lines"] = self.options["ellipsis"]
        if "caption" in self.options:
            caption = self.options["caption"] or self.arguments[0]
            node = _container_wrapper(self, node, caption)

        self.add_name(node)
        return [node]


_Command = namedtuple("Command", "command shell hide_standard_error working_directory setup")


class Command(_Command):
    """
    A command to be executed.
    """

    def __new__(
        cls, command, shell=False, hide_standard_error=False, working_directory="/", setup=None
    ):
        # `chdir()` resolves symlinks, so we need to resolve them too for
        # caching to make sure that different symlinks to the same directory
        # don't result in different cache keys.  Also normalize paths to make
        # sure that identical paths are also equal as strings.
        working_directory = os.path.normpath(os.path.realpath(working_directory))
        # Likewise, normalize the command now for better caching, and so
        # that we can present *exactly* what we run to the user.
        command = cls.__normalize_command(command, shell)
        return _Command.__new__(cls, command, shell, hide_standard_error, working_directory, setup)

    def id(self) -> str:
        f = io.StringIO()
        for item in self:
            f.write(str(item))
        return hashit(f.getvalue())

    @staticmethod
    def __normalize_command(command, shell):
        # Returns either a native string, to a tuple.
        if bytes is str and not isinstance(command, str) and hasattr(command, "encode"):
            # Python 2, given a unicode string
            command = command.encode(sys.getfilesystemencoding())
            assert isinstance(command, str)

        if not shell and isinstance(command, str):
            command = shlex.split(command)

        if isinstance(command, list):
            command = tuple(command)

        assert isinstance(command, (str, tuple)), command

        return command

    @classmethod
    def from_program_output_node(cls, node):
        """
        Create a command from a :class:`program_output` node.
        """
        extraargs = node.get("extraargs", "")
        command = (node["command"] + " " + extraargs).strip()
        return cls(
            command,
            node["use_shell"],
            node["hide_standard_error"],
            node["working_directory"],
            node.get("setup"),
        )

    def execute(self):
        """
        Execute this command.

        Return the :class:`~subprocess.Popen` object representing the running
        command.
        """
        if self.setup:
            with open(os.devnull, "a") as fh:
                p = Popen(
                    shlex.split(self.setup), stdout=fh, stderr=STDOUT, cwd=self.working_directory
                )
            p.wait()

        command = self.command
        global g_fp, g_path
        fd, g_path = tempfile.mkstemp()
        g_fp = os.fdopen(fd, "w")
        proc = Popen(
            command,
            shell=self.shell,
            stdout=g_fp,
            stderr=open(os.devnull, "a") if self.hide_standard_error else STDOUT,
            cwd=self.working_directory,
        )
        return proc

    def get_output(self):
        """
        Get the output of this command.

        Return a tuple ``(returncode, output)``.  ``returncode`` is the
        integral return code of the process, ``output`` is the output as
        unicode string, with final trailing spaces and new lines stripped.
        """
        global g_fp, g_path
        try:
            process = self.execute()
            process.wait()
        except Exception:
            g_fp.close()
            print(open(g_path).read())
            raise
        else:
            g_fp.close()
            output = open(g_path).read().rstrip()
        finally:
            os.remove(g_path)
            g_fp = g_path = None

        return process.returncode, output

    def __str__(self):
        command = self.command
        command = list(command) if isinstance(command, tuple) else command
        return repr(command)


class ProgramOutputCache:
    """
    Execute command and cache their output.

    This class is a mapping.  Its keys are :class:`Command` objects represeting
    command invocations.  Its values are tuples of the form ``(returncode,
    output)``, where ``returncode`` is the integral return code of the command,
    and ``output`` is the output as unicode string.

    The first time, a key is retrieved from this object, the command is
    invoked, and its result is cached.  Subsequent access to the same key
    returns the cached value.
    """

    def __init__(self):
        self.cache = {}

    def get(self, command, f):
        if command not in self.cache:
            if os.path.exists(f):
                with open(f) as fh:
                    cache = json.load(fh)
                returncode = cache["returncode"]
                output = cache["output"]
            else:
                returncode, output = command.get_output()
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f, "w") as fh:
                    json.dump({"returncode": returncode, "output": output}, fh, indent=2)
            self.cache[command] = (returncode, output)
        return self.cache[command]

    def __missing__(self, command):
        """
        Called, if a command was not found in the cache.

        ``command`` is an instance of :class:`Command`.
        """
        result = command.get_output()
        self[command] = result
        return result


def _prompt_template_as_unicode(app):
    tmpl = app.config.programoutput_prompt_template
    if isinstance(tmpl, bytes):
        for enc in "utf-8", sys.getfilesystemencoding():
            try:
                tmpl = tmpl.decode(enc)
            except UnicodeError:  # pragma: no cover
                pass
            else:
                app.config.programoutput_prompt_template = tmpl
                break
    return tmpl


def run_programs(app, doctree):
    """
    Execute all programs represented by ``program_output`` nodes in
    ``doctree``.  Each ``program_output`` node in ``doctree`` is then
    replaced with a node, that represents the output of this program.

    The program output is retrieved from the cache in
    ``app.env.programoutput_cache``.
    """
    # The node_class used to be switchable to `sphinxcontrib.ansi.ansi_literal_block`
    # if `app.config.programoutput_use_ansi` was set. But sphinxcontrib.ansi
    # is no longer available on PyPI, so we can't test that. And if we can't test it,
    # we can't support it.
    node_class = nodes.literal_block

    cache = app.env.programoutput_cache
    cache_d = os.path.join(app.env.srcdir, ".cache")
    for node in doctree.traverse(program_output):
        command = Command.from_program_output_node(node)
        f = os.path.join(cache_d, command.id())
        try:
            if node["nocache"]:
                returncode, output = command.get_output()
            else:
                returncode, output = cache.get(command, f)
        except EnvironmentError as error:
            error_message = "Command {0} failed: {1}".format(command, error)
            error_node = doctree.reporter.error(error_message, base_node=node)
            # Sphinx 1.8.0b1 started dropping all system_message nodes with a
            # level less than 5 by default (or 2 if `keep_warnings` is set to true).
            # This appears to be undocumented. Reporting failures is an important
            # part of what this extension does, so we raise the default level.
            error_node["level"] = 6
            node.replace_self(error_node)
        else:
            if not node["anyreturncode"] and returncode != node["returncode"]:
                logger.warning(
                    "Unexpected return code %s from command %r (output=%r)",
                    returncode,
                    command,
                    output,
                )

            # replace lines with ..., if ellipsis is specified

            # Recall that `output` is guaranteed to be a unicode string on
            # all versions of Python.
            if "strip_lines" in node:
                start, stop = node["strip_lines"]
                lines = output.splitlines()
                lines[start:stop] = ["..."]
                output = "\n".join(lines)

            if node["show_prompt"]:
                # The command in the node is also guaranteed to be
                # unicode, but the prompt template might not be. This
                # could be a native string on Python 2, or one with an
                # explicit b prefix on 2 or 3 (for some reason).
                # Attempt to decode it using UTF-8, preferentially, or
                # fallback to sys.getfilesystemencoding(). If all that fails, fall back
                # to the default encoding (which may have often worked before).
                prompt_template = _prompt_template_as_unicode(app)
                output = prompt_template.format(
                    command=node["command"], output=output, returncode=returncode
                )

            if node["silent"]:
                new_node = nodes.meta()
            else:
                new_node = node_class(output, output)
                new_node["language"] = "console"
            node.replace_self(new_node)


def init_cache(app):
    """
    Initialize the cache for program output at
    ``app.env.programoutput_cache``, if not already present (e.g. being
    loaded from a pickled environment).

    The cache is of type :class:`ProgramOutputCache`.
    """
    if not hasattr(app.env, "programoutput_cache"):
        app.env.programoutput_cache = ProgramOutputCache()


def setup(app):
    app.add_config_value("programoutput_prompt_template", "$ {command}\n{output}", "env")
    app.add_directive("program-output", ProgramOutputDirective)
    app.add_directive("command-output", ProgramOutputDirective)
    app.connect("builder-inited", init_cache)
    app.connect("doctree-read", run_programs)
    metadata = {"parallel_read_safe": True}
    return metadata


def hashit(arg, length=15):
    if isinstance(arg, (list, tuple)):
        arg = " ".join(arg)
    obj = hashlib.md5(arg.encode("utf-8"))
    return obj.hexdigest()[:length]
