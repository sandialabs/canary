import canary


@canary.hookimpl
def canary_subcommand() -> canary.CanarySubcommand:
    return canary.CanarySubcommand(
        name="my-command",
        description="My custom command",
        setup_parser=setup_parser,
        execute=my_command,
    )


def setup_parser(parser: canary.Parser) -> None:
    parser.add_plugin_argument("--my-option")


def my_command(args) -> None:
    print(f"I am running my command with my-option={args.my_option}")
