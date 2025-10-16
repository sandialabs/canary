# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import math
import statistics
from graphlib import TopologicalSorter
from typing import Callable
from typing import Generator
from typing import Sequence

import canary

logger = canary.get_logger(__name__)

AUTO = 1000001  # automically choose batch size
ONE_PER_BIN = 1000002  # One block per bin

GrouperType = Callable[[list["Block"]], list[list["Block"]]]


class Block:
    def __init__(
        self,
        id: str,
        width: int,
        height: int,
        dependencies: list["Block"] | None = None,
    ) -> None:
        self.id: str = id
        self.width: int = width
        self.height: int = height
        self.dependencies: list[Block] = []
        if dependencies:
            self.dependencies.extend(dependencies)
        self.fit: Node | None = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self):
        return f"Block({self.id}, {self.width}, {self.height})"

    def norm(self) -> float:
        return math.sqrt(self.width**2 + self.height**2)


class Node:
    """
    Defines an object Node for use in the packer function.  Represents the space that a block is
    placed.

    Args:
      size: The width and height of the node.
      origin: (x, y) coordinate of the top left of the node.

    Attributes:
      used: Boolean to determine if a node has been used.
      down: A node located beneath the current node.
      right: A node located to the right of the current node.
    """

    def __init__(self, origin: tuple[int, int], size: tuple[int, int]):
        self.origin: tuple[int, int] = origin
        self.size: tuple[int, int] = size
        self.used: bool = False
        self.down: Node | None = None
        self.right: Node | None = None


class Bin:
    def __init__(self, blocks: Sequence[Block] | None = None, width: int | None = None) -> None:
        self.blocks: list[Block] = []
        if blocks is not None:
            self.blocks.extend(blocks)

    def __iter__(self) -> Generator[Block, None, None]:
        for block in self.blocks:
            yield block

    def __len__(self) -> int:
        return len(self.blocks)

    def __bool__(self) -> bool:
        return len(self.blocks) > 0

    def __repr__(self) -> str:
        s = ", ".join(str(block) for block in self)
        return "Bin(%s)" % s

    def add(self, block: Block) -> None:
        self.blocks.append(block)

    def update(self, blocks: list[Block] | set[Block]) -> None:
        self.blocks.extend(blocks)

    def clear(self) -> None:
        self.blocks.clear()

    def norm(self) -> float:
        vector: list[float] = [0.0, 0.0]
        for block in self:
            vector[0] += block.width
            vector[1] += block.height
        return math.sqrt(vector[0] ** 2 + vector[1] ** 2)


def pack_by_count_atomic(blocks: Sequence[Block], count: int = 8) -> list[Bin]:
    """Partition blocks into ``count`` blocks.

    A note on the value of ``count``:

    * If ``count == ONE_PER_BIN``, tests are put into individual batches
    * If ``count == AUTO``, tests are put into batches automatically
    * If ``count >= 1``, tests are put into *at most* ``count`` batches, though it may be less.

    """
    if count <= 0:
        raise ValueError(f"{count=} must be > 0")
    if count == 1:
        return [Bin(blocks)]
    groups = groupby_dep(blocks)
    if count == AUTO:
        bins: list[Bin] = [Bin(list(group)) for group in groups if len(group) > 1]
        mean_bin_size = statistics.mean([b.norm() for b in bins])
        bin: Bin = Bin()
        # Handle groups of length 1 individually
        for group in groups:
            if len(group) == 1:
                bin.update(group)
                if bin.norm() >= mean_bin_size:
                    bins.append(Bin(list(group)))
                    bin.clear()
        if bin:
            bins.append(bin)
        return bins
    else:
        bins: list[Bin] = [Bin() for i in range(count)]
        for group in groups:
            bin = min(bins, key=lambda b: b.norm())
            bin.update(group)
        return bins


def pack_by_count(
    blocks: Sequence[Block],
    count: int = 8,
    grouper: GrouperType | None = None,
) -> list[Bin]:
    """Pack blocks into ``count`` bins such that each bin has no
    intra-dependencies.  Bin can depend on other bins.

    A note on the value of ``count``:

    * If ``count == ONE_PER_BIN``, tests are put into individual batches
    * If ``count == AUTO``, tests are batched such that each batch contains no inter-batch dependencies
    * If ``count >= 1``, tests are put into *at most* ``count`` batches, though it may be less.

    """
    if count == ONE_PER_BIN:
        return [Bin([block]) for block in blocks]
    elif count == 1:
        return [Bin(blocks)]
    graph = {}
    for block in blocks:
        graph[block] = [dep for dep in block.dependencies if dep in blocks]
    ts = TopologicalSorter(graph)
    ts.prepare()
    sizes: list[float] = []
    groups: list[list[Block]] = []
    while ts.is_active():
        ready = ts.get_ready()
        if grouper is not None:
            groups.extend(grouper(ready))
        else:
            groups.append(list(ready))
        sizes.append(sum(b.norm() for b in groups[-1]))
        ts.done(*ready)
    if count == AUTO:
        return [Bin(group) for group in groups]
    if len(groups) > count:
        raise ValueError(f"{count=} insufficient to partition blocks")
    # determine the number of bins each partition will receive
    total_size = sum(sizes)
    ix = sorted(range(len(groups)), key=lambda i: sizes[i])
    groups = [groups[i] for i in ix]
    sizes = [sizes[i] for i in ix]
    nbins_each = [max(1, math.floor(count * t / total_size)) for t in sizes[:-1]]
    nbins_each.append(count - sum(nbins_each))
    bins: list[Bin] = []
    for i, group in enumerate(groups):
        tmp_bins: list[Bin] = [Bin() for _ in range(nbins_each[i])]
        for block in group:
            b = min(tmp_bins, key=lambda b: b.norm())
            b.add(block)
        bins.extend([b for b in tmp_bins if len(b)])
    return bins


def pack_to_height(
    blocks: Sequence[Block],
    height: int = 1800,
    width: int | None = None,
    grouper: Callable[[list[Block]], list[list[Block]]] | None = None,
) -> list[Bin]:
    """Partition blocks by tiling in the 2D space defined by width x height"""
    logger.debug(f"Partitioning {len(blocks)} blocks")

    if width is not None:
        errors = 0
        for block in blocks:
            if block.width > width:
                errors += 1
                logger.error(f"{block.width=} > target {width=}")
        if errors:
            raise ValueError("Stopping due to previous errors")

    def _pack_ready_nodes(packer: "Packer", bins: list[Bin], ready: list[Block]) -> None:
        max_width = max(block.width for block in ready)
        target_width = max_width if width is None else width
        max_height = max(block.height for block in ready)
        target_height = int(max(max_height, height))
        packer.pack(ready, target_width, target_height)
        bins.append(Bin([map[b.id] for b in ready if b.fit]))
        unfit = [block for block in ready if not block.fit]
        while unfit:
            max_width = max(block.width for block in unfit)
            target_width = max_width if width is None else width
            target_height = int(max(max_height, height))
            packer.pack(unfit, target_width, target_height)
            bins.append(Bin([map[b.id] for b in unfit if b.fit]))
            tmp = [block for block in unfit if not block.fit]
            if len(tmp) == len(unfit):
                raise RuntimeError("Unable to partition blocks")
            unfit = tmp

    map: dict[str, Block] = {block.id: block for block in blocks}
    graph: dict[Block, list[Block]] = {}
    for block in blocks:
        graph[block] = [dep for dep in block.dependencies if dep in blocks]
    ts = TopologicalSorter(graph)
    ts.prepare()
    packer = Packer()
    bins: list[Bin] = []
    while ts.is_active():
        ready = sorted(ts.get_ready(), key=lambda b: b.norm(), reverse=True)
        if grouper is not None:
            for group in grouper(ready):
                _pack_ready_nodes(packer, bins, group)
        else:
            _pack_ready_nodes(packer, bins, ready)
        ts.done(*ready)
    if len(blocks) != sum([len(bin) for bin in bins]):
        raise ValueError("Incorrect partition lengths!")
    logger.debug(f"Partitioned {len(blocks)} test cases in to {len(bins)} bins")
    return [bin for bin in bins if len(bin)]


def groupby_dep(blocks: Sequence[Block]) -> list[set[Block]]:
    """Group cases such that a case and any of its dependencies are in the same
    group
    """
    sets = [{block} | set(block.dependencies) for block in blocks]
    groups: list[set[Block]] = []
    while sets:
        first, *rest = sets
        combined = True
        while combined:
            combined = False
            for s in rest:
                if first & s:
                    first |= s
                    s.clear()
                    combined = True
        groups.append(first)
        sets = rest
    groups = [_ for _ in groups if _]
    if len(blocks) != sum([len(group) for group in groups]):
        raise ValueError("Incorrect partition lengths!")
    return groups


# modified from https://gist.github.com/shihrer/aa90d023ae0f7662919f


class Packer:
    """Pack a list of blocks"""

    def __init__(self) -> None:
        self.root: Node | None = None
        self.auto: list[bool] = [False, False]

    def pack(
        self, blocks: list[Block], width: int | None = None, height: int | None = None
    ) -> None:
        """Initiates the packing."""
        self.auto.clear()
        self.auto.extend((False, False))
        if width is None:
            self.auto[0] = True
            width = math.ceil(1.5 * max(block.width for block in blocks))
        if height is None:
            self.auto[1] = True
            height = math.ceil(1.5 * max(block.height for block in blocks))
        self.root = Node((0, 0), (width, height))
        for block in blocks:
            node = self.find_node(self.root, (block.width, block.height))
            if node is not None:
                block.fit = self.split_node(node, (block.width, block.height))
            else:
                block.fit = self.grow_node((block.width, block.height))
        return None

    def find_node(self, node: Node, size: tuple[int, int]) -> Node | None:
        if node.used:
            assert node.right is not None and node.down is not None
            return self.find_node(node.right, size) or self.find_node(node.down, size)
        elif (size[0] <= node.size[0]) and (size[1] <= node.size[1]):
            return node
        else:
            return None

    def split_node(self, node: Node, size: tuple[int, int]) -> Node:
        node.used = True
        node.down = Node(
            (node.origin[0], node.origin[1] + size[1]), (node.size[0], node.size[1] - size[1])
        )
        node.right = Node(
            (node.origin[0] + size[0], node.origin[1]), (node.size[0] - size[0], size[1])
        )
        return node

    def grow_node(self, size: tuple[int, int]) -> Node | None:
        assert self.root is not None
        can_go_right = self.auto[0] and size[1] <= self.root.size[1]
        can_go_down = self.auto[1] and size[0] <= self.root.size[0]

        should_go_right = can_go_right and (self.root.size[1] >= (self.root.size[0] + size[0]))
        should_go_down = can_go_down and (self.root.size[0] >= (self.root.size[1] + size[1]))

        if should_go_right:
            return self.grow_right(size)
        elif should_go_down:
            return self.grow_down(size)
        elif can_go_right:
            return self.grow_right(size)
        elif can_go_down:
            return self.grow_down(size)
        else:
            return None

    def grow_right(self, size: tuple[int, int]) -> Node | None:
        assert self.root is not None
        root = Node((0, 0), (self.root.size[0] + size[0], self.root.size[1]))
        root.used = True
        root.down = self.root
        root.right = Node((self.root.size[0], 0), (size[0], self.root.size[1]))

        self.root = root

        node = self.find_node(self.root, size)
        if node is not None:
            return self.split_node(node, size)
        else:
            return None

    def grow_down(self, size: tuple[int, int]) -> Node | None:
        assert self.root is not None
        root = Node((0, 0), (self.root.size[0], self.root.size[1] + size[1]))
        root.used = True
        root.down = Node((0, self.root.size[1]), (self.root.size[0], size[1]))
        root.right = self.root

        self.root = root

        node = self.find_node(self.root, size)
        if node is not None:
            return self.split_node(node, size)
        else:
            return None


def perimeter(blocks: list[Block]) -> tuple[int, int]:
    max_x = max_y = 0
    for block in blocks:
        if block.fit is None:
            continue
        max_x = max(max_x, block.fit.origin[0] + block.fit.size[0])
        max_y = max(max_y, block.fit.origin[1] + block.fit.size[1])
    return max_x, max_y
