import math
import os
from types import SimpleNamespace


def compute_resource_allocations(
    *, machine_config: SimpleNamespace, ranks=None, ranks_per_socket=None
):
    """Return basic information about how to allocate resources on this machine

    Parameters
    ----------
    ranks : int
        The number of ranks to use for a job
    ranks_per_socket : int
        Number of ranks per socket, for performance use

    Returns
    -------
    SimpleNamespace

    """

    # System settings
    sockets_per_node = machine_config.sockets_per_node or 1
    cores_per_socket = machine_config.cores_per_socket or os.cpu_count()

    if ranks is None and ranks_per_socket is not None:
        # Raise an error since there is no reliable way of finding the number of
        # available nodes
        raise ValueError("'ranks_per_socket' requires 'ranks' also be defined")
    elif ranks is None and ranks_per_socket is None:
        ranks = ranks_per_socket = 1
        nodes = 1
    elif ranks is not None and ranks_per_socket is None:
        ranks_per_socket = min(ranks, cores_per_socket)
        nodes = int(math.ceil(ranks / cores_per_socket / sockets_per_node))
    else:
        nodes = int(math.ceil(ranks / ranks_per_socket / sockets_per_node))

    sockets = int(math.ceil(ranks / ranks_per_socket))

    ns = SimpleNamespace(
        np=ranks,
        ranks=ranks,
        ranks_per_socket=ranks_per_socket,
        nodes=nodes,
        sockets=sockets,
    )

    return ns


def get_num_nodes(default=None):
    if "SLURM_NNODES" in os.environ:
        return int(os.environ["SLURM_NNODES"])
    elif "PBS_NODEFILE" in os.environ:
        with open(os.environ["PBS_NODEFILE"]) as fh:
            nodes = [x for x in fh.readlines() if x.split()]
            return len(nodes)
    return default
