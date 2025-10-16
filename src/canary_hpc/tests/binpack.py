import canary_hpc.binpack


def test_binpack():
    blocks = []
    for i in range(1, 13):
        blocks.append(canary_hpc.binpack.Block(f"a{i}", i, 1))
    bins = canary_hpc.binpack.pack_to_height(blocks, width=12, height=3)
    extents = [4, 8, 12]
    bins = canary_hpc.binpack.pack_to_height(blocks, height=5, grouper=Grouper(extents))


class Grouper:
    def __init__(self, extents):
        self.extents = extents

    def __call__(self, blocks):
        groups = {}
        for block in blocks:
            for extent in sorted(self.extents):
                if block.width <= extent:
                    groups.setdefault(extent, []).append(block)
                    break
        return list(groups.values())
