import nvtest


@nvtest.plugin.register(scope="argparse", stage="add_command")
def add_sessions(config: nvtest.Config, parser: nvtest.Parser) -> None:
    from ..session.base import Session
    from ..session.config import Config
    from ..session.describe import Describe
    from ..session.find import Find
    from ..session.info import Info
    from ..session.merge_batches import MergeBatches
    from ..session.run import Run
#    from ..session.run_batch import RunBatch
#    from ..session.run_batched import RunBatched
#    from ..session.run_case import RunCase
#    from ..session.setup import Setup
#    from ..session.create_batches import CreateBatches

    for subclass in Session.registry:
        parser.add_command(subclass)
