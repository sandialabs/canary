# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import random
from typing import Iterable


def random_name(seed: int | None = None):
    rng = random.Random(seed)
    """Generate a two-part hyphenated name: <adjective>-<noun>"""
    return f"{rng.choice(adjectives)}-{rng.choice(nouns)}"


def unique_random_name(
    existing_names: Iterable[str],
    max_samples: int = 20,
    seed: int | None = None,
) -> str:
    """Attempt to generate a random name that is not in `existing_names` within `max_samples`.

    Raises `ValueError` if unable to generate a unique name
    """
    for _ in range(max_samples):
        name = random_name(seed)
        if name not in existing_names:
            return name
    else:
        raise ValueError(
            f"unable to generate name outside {existing_names} in {max_samples} attempts"
        )


adjectives = """
amber amethyst antique apple aqua aquamarine arctic ash azure beige black blue blushing
bone bronze brown burgundy caramel cardinal carmine cerulean charcoal chartreuse cherry
chestnut chocolate citrine clay cobalt coffee copper coral cornflower cream crimson
cyan denim desert driftwood emerald evergreen fawn fern firebrick flax forest fuchsia
garnet glacier gold golden granite graphite gray green gunmetal honey indigo ink ivory
jade lavender lemon lilac lime linen magenta maroon midnight mint moss mulberry navy
obsidian ocean ochre olive onyx opal orange orchid pale pearl pewter pine pink plum
porcelain purple quartz raven red rose ruby rust saffron sage sand sandstone
scarlet seafoam sepia shadow sienna silver slate snow steel stone storm sunlit tan
taupe teal terra terracotta titanium turquoise ultramarine umber velvet vermilion
violet viridian white wild windworn winter yellow
agile ancient arcane ardent austere bold brave brisk bright calm candid careful
celestial centered certain clever coastal cosmic crisp curious daring deft devoted
diligent distant dapper eager electric elusive earnest even faithful fierce fiery
focused friendly frosty gentle grand gritty hearty hidden humble icy ideal keen kind
lively lunar loyal lucid lucky mellow mighty misty modern modest nimble noble noisy
patient playful polished proud quick quiet radiant rapid rare ready resolute robust
rugged rustic sacred savvy serene sharp silent simple smooth soft solar solid steady
stoic stormy sturdy subtle swift tidy tranquil true valiant vast vigilant vivid warm
wary wild wise
""".split()

nouns = """
acorn alder anvil apex arch arrow ash atlas aurora autumn axe badger bay beacon bear
beetle bison blade bluff boulder breeze bridge brook buffalo canyon capstan castle
cedar cinder cliff cloud cobra comet compass conifer coral cove coyote crane creek
crest crow crystal current dawn delta desert dingo dolphin dune eagle echo ember
falcon fern finch fjord flame flint floe fox galaxy gale garden gecko glacier glade
gorge granite grove gull harbor hawk heron hill horizon horsehound isthmus jaguar
kernel kestrel key krait lagoon lake lantern lark leaf leopard lemur lion lobo lynx
marten meadow meteor mirage mirror monolith moon moose moraine nebula needle night
oasis obsidian octant orca orchard otter owl panther pass pebble peregrine phoenix
pine puma quail quarry rabbit raven reef ridge river robin rocket rook sail salmon
savanna seal shadow shark shore silo sky slope snowfield sparrow sphinx spring spur
stone storm summit sun swale swan talon tarn thunder tide tiger trail tree turtle
valley veil viper voyage warden wave whale whisper willow wind wolf wolverine wren
""".split()
