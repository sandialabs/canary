# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import math
import statistics
from graphlib import TopologicalSorter
from typing import Generator
from typing import Sequence
from typing import Literal

import canary

logger = canary.get_logger(__name__)

AUTO = 1000001  # automically choose batch size
ONE_PER_BUCKET = 1000002  # One block per bucket


class Block:
    def __init__(
        self,
        id: str,
        width: int,
        height: int,
        extent: int | None = None,
        dependencies: list["Block"] | None = None,
    ) -> None:
        self.id: str = id
        self.width: int = width
        self.height: int = height
        self.extent: int = extent or width
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

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


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


class Bucket:
    def __init__(self, blocks: Sequence[Block] | None = None) -> None:
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

    def add(self, block: Block) -> None:
        self.blocks.append(block)

    def update(self, blocks: list[Block] | set[Block]) -> None:
        self.blocks.extend(blocks)

    def clear(self) -> None:
        self.blocks.clear()

    def size(self) -> float:
        vector: list[float] = [0.0, 0.0]
        for block in self:
            vector[0] += block.width
            vector[1] += block.height
        return math.sqrt(vector[0] ** 2 + vector[1] ** 2)


def pack_by_count_atomic(blocks: Sequence[Block], count: int = 8) -> list[Bucket]:
    """Partition blocks into ``count`` blocks.

    A note on the value of ``count``:

    * If ``count == ONE_PER_BUCKET``, tests are put into individual batches
    * If ``count == AUTO``, tests are put into batches automatically
    * If ``count >= 1``, tests are put into *at most* ``count`` batches, though it may be less.

    """
    if count <= 0:
        raise ValueError(f"{count=} must be > 0")
    if count == 1:
        return [Bucket(blocks)]
    groups = groupby_dep(blocks)
    if count == AUTO:
        buckets: list[Bucket] = [Bucket(list(group)) for group in groups if len(group) > 1]
        mean_bucket_size = statistics.mean([b.size() for b in buckets])
        bucket: Bucket = Bucket()
        # Handle groups of length 1 individually
        for group in groups:
            if len(group) == 1:
                bucket.update(group)
                if bucket.size() >= mean_bucket_size:
                    buckets.append(Bucket(list(group)))
                    bucket.clear()
        if bucket:
            buckets.append(bucket)
        return buckets
    else:
        buckets: list[Bucket] = [Bucket() for i in range(count)]
        for group in groups:
            bucket = min(buckets, key=lambda b: b.size())
            bucket.update(group)
        return buckets


def pack_by_count(
    blocks: Sequence[Block], count: int = 8, groupby: Literal["extent", "auto"] = "auto"
) -> list[Bucket]:
    """Pack blocks into ``count`` buckets such that each bucket has no
    intra-dependencies.  Buckets can depend on other buckets.

    A note on the value of ``count``:

    * If ``count == ONE_PER_BUCKET``, tests are put into individual batches
    * If ``count == AUTO``, tests are batched such that each batch contains no inter-batch dependencies
    * If ``count >= 1``, tests are put into *at most* ``count`` batches, though it may be less.

    """
    if count == ONE_PER_BUCKET:
        return [Bucket([block]) for block in blocks]
    elif count == 1:
        return [Bucket(blocks)]
    graph = {}
    for block in blocks:
        graph[block] = [dep for dep in block.dependencies if dep in blocks]
    ts = TopologicalSorter(graph)
    ts.prepare()
    sizes: list[float] = []
    groups: list[list[Block]] = []
    while ts.is_active():
        ready = ts.get_ready()
        if groupby == "extent":
            egroups: dict[int, list[Block]] = {}
            for block in ready:
                egroups.setdefault(block.extent, []).append(block)
            groups.extend(egroups.values())
        else:
            groups.append(list(ready))
        sizes.append(sum(b.norm() for b in groups[-1]))
        ts.done(*ready)
    if count == AUTO:
        return [Bucket(group) for group in groups]
    if len(groups) > count:
        raise ValueError(f"{count=} insufficient to partition blocks")
    # determine the number of buckets each partition will receive
    total_size = sum(sizes)
    ix = sorted(range(len(groups)), key=lambda i: sizes[i])
    groups = [groups[i] for i in ix]
    sizes = [sizes[i] for i in ix]
    nbuckets_each = [max(1, math.floor(count * t / total_size)) for t in sizes[:-1]]
    nbuckets_each.append(count - sum(nbuckets_each))
    buckets: list[Bucket] = []
    for i, group in enumerate(groups):
        tmp_buckets: list[Bucket] = [Bucket() for _ in range(nbuckets_each[i])]
        for block in group:
            b = min(tmp_buckets, key=lambda b: b.size())
            b.add(block)
        buckets.extend([b for b in tmp_buckets if len(b)])
    return buckets


def pack_to_height(
    blocks: Sequence[Block],
    height: int = 1800,
    groupby: Literal["extent", "auto"] = "auto",
) -> list[Bucket]:
    """Partition blocks by tiling in the 2D space defined by width x height"""
    logger.debug(f"Partitioning {len(blocks)} blocks")

    def _pack_ready_nodes(packer: "Packer", buckets: list[Bucket], ready: list[Block]) -> None:
        width = max(block.extent for block in ready)
        max_height = max(block.height for block in ready)
        target_height = int(max(max_height, height))
        packer.pack(ready, width, target_height)
        buckets.append(Bucket([map[b.id] for b in ready if b.fit]))
        unfit = [block for block in ready if not block.fit]
        while unfit:
            width = max(block.extent for block in unfit)
            target_height = int(max(max_height, height))
            packer.pack(unfit, width, target_height)
            buckets.append(Bucket([map[b.id] for b in unfit if b.fit]))
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
    buckets: list[Bucket] = []
    while ts.is_active():
        ready = sorted(ts.get_ready(), key=lambda b: b.norm(), reverse=True)
        if groupby == "extent":
            egroups: dict[int, list[Block]] = {}
            for block in ready:
                egroups.setdefault(block.extent, []).append(block)
            for group in egroups.values():
                _pack_ready_nodes(packer, buckets, group)
        else:
            _pack_ready_nodes(packer, buckets, ready)
        ts.done(*ready)
    if len(blocks) != sum([len(bucket) for bucket in buckets]):
        raise ValueError("Incorrect partition lengths!")
    logger.debug(f"Partitioned {len(blocks)} test cases in to {len(buckets)} buckets")
    return [bucket for bucket in buckets if len(bucket)]


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
            width = math.ceil(1.5 * max(block.size[0] for block in blocks))
        if height is None:
            self.auto[1] = True
            height = math.ceil(1.5 * max(block.size[1] for block in blocks))
        self.root = Node((0, 0), (width, height))
        for block in blocks:
            node = self.find_node(self.root, block.size)
            if node is not None:
                block.fit = self.split_node(node, block.size)
            else:
                block.fit = self.grow_node(block.size)
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
