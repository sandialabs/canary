# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from _canary.util import names


def test_random_name_with_seed_is_repeatable():
    seed = 1
    assert len({names.random_name(seed=seed) for _ in range(10)}) == 1


def test_random_name_does_not_repeat_for_small_count():
    N = 30
    # set the random number generator seed so this test is repeatable
    names.random_name(seed=1)
    random_names = {names.random_name() for _ in range(N)}
    print(random_names)
    assert len(random_names) == N


def test_unique_random_name_raises_if_unable_to_generate_name():
    seed = 1
    existing_names = {names.random_name(seed=seed)}
    try:
        _ = names.unique_random_name(existing_names, seed=seed)
        assert False
    except ValueError as e:
        print(e)
        assert True
    except:
        assert False


def test_unique_random_name():
    seed = 1
    N = 20
    names.random_name(seed=seed)
    existing_names = {names.random_name() for _ in range(N)}

    # reset the seed
    names.random_name(seed=seed)
    unique_name = names.unique_random_name(existing_names=existing_names, max_samples=N + 1)

    assert unique_name not in existing_names
