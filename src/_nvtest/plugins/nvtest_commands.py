import nvtest


@nvtest.plugin.register(scope="argparse", stage="add_command")
def add_sessions(config: nvtest.Config, parser: nvtest.Parser) -> None:
    from ..session.base import Session
    from ..session.config import Config
    from ..session.describe import Describe
    from ..session.find import Find
    from ..session.info import Info
    from ..session.run import Run

    #    from ..session.merge_batches import MergeBatches

    for subclass in Session.registry:
        parser.add_command(subclass)
