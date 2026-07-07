# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import canary_hpc.binpack


def _flatten_bins(bins):
    return [block for bin_ in bins for block in bin_.blocks]


def _assert_same_blocks_once(actual_blocks, expected_blocks):
    """Assert that the same block objects appear exactly once."""
    assert len(actual_blocks) == len(expected_blocks)
    assert {id(block) for block in actual_blocks} == {id(block) for block in expected_blocks}


def _placed_extents(blocks):
    """Return the occupied width/height based on block.fit placements."""
    max_x = 0
    max_y = 0

    for block in blocks:
        assert block.fit is not None, f"{block.id} was not placed"

        max_x = max(max_x, block.fit.origin[0] + block.width)
        max_y = max(max_y, block.fit.origin[1] + block.height)

    return max_x, max_y


def _bucket_for_width(width, extents):
    for extent in sorted(extents):
        if width <= extent:
            return extent
    raise ValueError(f"{width=} does not fit in {extents=}")


def test_pack_to_height_places_every_block_once_and_respects_bounds():
    blocks = [canary_hpc.binpack.Block(f"a{i}", i, 1) for i in range(1, 13)]

    bins = canary_hpc.binpack.pack_to_height(blocks, width=12, height=3)

    _assert_same_blocks_once(_flatten_bins(bins), blocks)

    for bin_ in bins:
        width, height = _placed_extents(bin_.blocks)
        assert width <= 12
        assert height <= 3


def test_pack_to_height_with_grouper_places_every_block_once():
    blocks = [canary_hpc.binpack.Block(f"a{i}", i, 1) for i in range(1, 13)]

    extents = [4, 8, 12]
    bins = canary_hpc.binpack.pack_to_height(blocks, height=5, grouper=Grouper(extents))

    _assert_same_blocks_once(_flatten_bins(bins), blocks)

    for bin_ in bins:
        width, height = _placed_extents(bin_.blocks)
        assert height <= 5

        bucket_ids = {_bucket_for_width(block.width, extents) for block in bin_.blocks}

        assert len(bucket_ids) == 1
        assert width <= next(iter(bucket_ids))


def test_grouper_partitions_by_first_matching_extent():
    blocks = [
        canary_hpc.binpack.Block("w1", 1, 1),
        canary_hpc.binpack.Block("w4", 4, 1),
        canary_hpc.binpack.Block("w5", 5, 1),
        canary_hpc.binpack.Block("w8", 8, 1),
        canary_hpc.binpack.Block("w9", 9, 1),
        canary_hpc.binpack.Block("w12", 12, 1),
    ]

    groups = Grouper([4, 8, 12])(blocks)

    assert [[block.id for block in group] for group in groups] == [
        ["w1", "w4"],
        ["w5", "w8"],
        ["w9", "w12"],
    ]


def test_grouper_rejects_block_that_fits_no_extent():
    blocks = [canary_hpc.binpack.Block("ok", 12, 1), canary_hpc.binpack.Block("too-wide", 13, 1)]

    with pytest.raises(ValueError, match="does not fit"):
        Grouper([4, 8, 12])(blocks)


def test_pack_to_height_rejects_grouper_that_drops_blocks():
    blocks = [canary_hpc.binpack.Block(f"a{i}", i, 1) for i in range(1, 5)]

    class DroppingGrouper:
        def __call__(self, blocks):
            return [list(blocks[:-1])]

    with pytest.raises(ValueError, match="partition|drop|drops|duplicate|duplicates"):
        canary_hpc.binpack.pack_to_height(blocks, height=2, grouper=DroppingGrouper())


def test_pack_to_height_rejects_grouper_that_duplicates_blocks():
    blocks = [canary_hpc.binpack.Block(f"a{i}", i, 1) for i in range(1, 5)]

    class DuplicatingGrouper:
        def __call__(self, blocks):
            return [list(blocks) + [blocks[0]]]

    with pytest.raises(ValueError, match="partition|drop|drops|duplicate|duplicates"):
        canary_hpc.binpack.pack_to_height(blocks, height=2, grouper=DuplicatingGrouper())


class Grouper:
    def __init__(self, extents):
        self.extents = sorted(extents)

    def __call__(self, blocks):
        groups = {}

        for block in blocks:
            for extent in self.extents:
                if block.width <= extent:
                    groups.setdefault(extent, []).append(block)
                    break
            else:
                raise ValueError(
                    f"Block {block.id!r} with width {block.width} does not fit "
                    f"in any extent: {self.extents}"
                )

        return list(groups.values())
