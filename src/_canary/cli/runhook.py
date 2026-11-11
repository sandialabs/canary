# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from .. import app
from .. import config
from .. import rerun
from ..app.pathspec import TagRequest
from ..app.pathspec import classify_pathspec
from ..plugins.hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(RunHook())


class RunHook(CanarySubcommand):
    name = "runhook"
    description = "Replay stored hooks against existing results"
    epilog = (
        "Examples:\n\n"
        "[pad]canary runhook canary_runtest_finish\n\n"
        "[pad]canary runhook canary_runtest_finish --only failed\n\n"
        "[pad]canary runhook canary_runtest_finish -k fast\n\n"
        "[pad]canary runhook canary_runtest_finish --session latest TEST_ID\n\n"
        "[pad]canary runhook canary_sessionfinish --session latest"
    )

    def setup_parser(self, parser: "Parser") -> None:
        sub = parser.add_subparsers(dest="runhook_command", metavar="HOOK")

        finish = sub.add_parser("canary_runtest_finish", help="Replay the per-job finish hook")
        finish.add_argument(
            "items",
            nargs="*",
            help="Optional spec ids, view paths, or tag names [default: configured run tag in latest session]",
        )
        finish.add_argument(
            "--session",
            default="latest",
            help='Session name, prefix, or "latest" used when defaulting to stored session results',
        )
        rerun.setup_parser(finish)
        finish.add_argument(
            "-k",
            dest="keyword_exprs",
            metavar="expression",
            action="append",
            help="Restrict hook replay to stored jobs matching keyword expression",
        )
        finish.set_defaults(_runhook_handler=self.run_finish)

        sessionfinish = sub.add_parser(
            "canary_sessionfinish", help="Replay the session finish hook"
        )
        sessionfinish.add_argument(
            "--session",
            default="latest",
            help='Session name, prefix, or "latest" identifying the stored session to replay',
        )
        sessionfinish.set_defaults(_runhook_handler=self.run_sessionfinish)

    def execute(self, args: argparse.Namespace) -> int:
        handler = getattr(args, "_runhook_handler", None)
        if handler is None:
            return 0
        return handler(args)

    def run_finish(self, args: argparse.Namespace) -> int:
        request = _build_request(args.items)
        return app.run_hook(
            "canary_runtest_finish",
            request,
            app.RunHookOptions(
                keyword_exprs=args.keyword_exprs, only=args.only, session=args.session
            ),
        )

    def run_sessionfinish(self, args: argparse.Namespace) -> int:
        return app.run_hook("canary_sessionfinish", None, app.RunHookOptions(session=args.session))


def _build_request(items: list[str]):
    if not items:
        return TagRequest(value=config.get("run:default_tag"))
    builder = classify_pathspec(items)
    if builder.errors:
        raise ValueError("\n".join(builder.errors))
    request = builder.finalize()
    if request is None:
        return TagRequest(value=config.get("run:default_tag"))
    if request.kind == "scanpaths":
        raise ValueError("runhook does not accept scan path requests")
    return request
