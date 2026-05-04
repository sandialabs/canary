import pytest

from _canary.paramset import ParameterSet
from _canary.paramset import is_scalar
from _canary.paramset import transpose


def test_init_validates_row_length():
    with pytest.raises(ValueError, match=r"expected 2 items in row 1"):
        ParameterSet(keys=["a", "b"], values=[(1,)])


def test_iter_yields_key_value_pairs():
    ps = ParameterSet(keys=["a", "b"], values=[(1, 2), (3, 4)])
    rows = list(ps)
    assert rows == [[("a", 1), ("b", 2)], [("a", 3), ("b", 4)]]


def test_describe_format():
    ps = ParameterSet(keys=["a", "b"], values=[(1, 2), (3, 4)])
    s = ps.describe()
    assert s.startswith("a,b = ")
    assert "1,2" in s
    assert "3,4" in s


def test_list_parameter_space_single_name_scalar_values():
    ps = ParameterSet.list_parameter_space("a", [1, 2, 3])
    assert ps.keys == ["a"]
    assert ps.values == [[1], [2], [3]]


def test_list_parameter_space_multiple_names_rows():
    ps = ParameterSet.list_parameter_space("a,b", [(1, 2), (3, 4)])
    assert ps.keys == ["a", "b"]
    assert ps.values == [[1, 2], [3, 4]]


def test_list_parameter_space_names_sequence():
    ps = ParameterSet.list_parameter_space(["a", "b"], [(1, 2)])
    assert ps.keys == ["a", "b"]
    assert ps.values == [[1, 2]]


def test_list_parameter_space_mismatched_row_length_raises():
    with pytest.raises(ValueError) as ei:
        ParameterSet.list_parameter_space("a,b", [(1, 2, 3)], file="X.pyt")
    msg = str(ei.value)
    assert "X.pyt" in msg
    assert "number of names" in msg


def test_centered_parameter_space_basic_shape():
    # names: a,b
    # a: x0=0, dx=5, steps=1 -> -5, +5
    # b: x0=0, dx=1, steps=1 -> -1, +1
    # total = 1 + 2*(1+1)=5 rows
    ps = ParameterSet.centered_parameter_space("a,b", [(0, 5, 1), (0, 1, 1)], file="F")
    assert ps.keys == ["a", "b"]
    assert len(ps.values) == 5
    assert ps.values[0] == [0, 0]
    assert [-5, 0] in ps.values
    assert [5, 0] in ps.values
    assert [0, -1] in ps.values
    assert [0, 1] in ps.values


def test_centered_parameter_space_requires_more_than_one_name():
    with pytest.raises(ValueError, match="expected more than 1 parameter name"):
        ParameterSet.centered_parameter_space("a", [(0, 1, 1)], file="F")


def test_centered_parameter_space_len_names_equals_len_values():
    with pytest.raises(ValueError, match="expected len\\(names\\) == len\\(values\\)"):
        ParameterSet.centered_parameter_space("a,b", [(0, 1, 1)], file="F")


def test_centered_parameter_space_each_item_len_3():
    with pytest.raises(ValueError, match=r"expected len\(argvalues\[0\]\) == 3"):
        ParameterSet.centered_parameter_space("a,b", [(0, 1), (0, 1, 1)], file="F")


def test_random_parameter_space_deterministic_for_seed():
    ps1 = ParameterSet.random_parameter_space(
        "a,b", [(0.0, 1.0), (10.0, 20.0)], samples=3, random_seed=1234.0
    )
    ps2 = ParameterSet.random_parameter_space(
        "a,b", [(0.0, 1.0), (10.0, 20.0)], samples=3, random_seed=1234.0
    )
    assert ps1.keys == ["a", "b"]
    assert ps1.values == ps2.values
    assert len(ps1.values) == 3
    # each row has 2 columns
    assert all(len(row) == 2 for row in ps1.values)


def test_random_parameter_space_requires_more_than_one_name():
    with pytest.raises(ValueError, match="expected more than 1 parameter name"):
        ParameterSet.random_parameter_space("a", [(0.0, 1.0)], samples=3, random_seed=0.0, file="F")


def test_random_parameter_space_len_names_equals_len_values():
    with pytest.raises(ValueError, match="expected len\\(names\\) == len\\(values\\)"):
        ParameterSet.random_parameter_space(
            "a,b", [(0.0, 1.0)], samples=3, random_seed=0.0, file="F"
        )


def test_random_parameter_space_each_item_len_2():
    with pytest.raises(ValueError, match=r"expected len\(argvalues\[0\]\) == 2"):
        ParameterSet.random_parameter_space(
            "a,b", [(0.0, 1.0, 2.0), (0.0, 1.0)], samples=3, random_seed=0.0, file="F"
        )


def test_combine_empty_is_empty():
    assert ParameterSet.combine([]) == []


def test_combine_single_paramset_no_duplicates():
    ps = ParameterSet.list_parameter_space("a", [1, 2, 2, 3])
    combined = ParameterSet.combine([ps])
    assert combined == [{"a": 1}, {"a": 2}, {"a": 3}]


def test_combine_cartesian_product_and_dedup():
    ps1 = ParameterSet.list_parameter_space("a", [1, 1, 2])
    ps2 = ParameterSet.list_parameter_space("b", [10, 20])
    out = ParameterSet.combine([ps1, ps2])
    # should be 4 unique combos: (1,10) (1,20) (2,10) (2,20)
    assert len(out) == 4
    assert {"a": 1, "b": 10} in out
    assert {"a": 1, "b": 20} in out
    assert {"a": 2, "b": 10} in out
    assert {"a": 2, "b": 20} in out


def test_combine_multiple_keys_flattened_order():
    ps1 = ParameterSet.list_parameter_space("a,b", [(1, 2)])
    ps2 = ParameterSet.list_parameter_space("c", [3])
    out = ParameterSet.combine([ps1, ps2])
    assert out == [{"a": 1, "b": 2, "c": 3}]


def test_is_scalar():
    assert is_scalar(1)
    assert is_scalar(1.0)
    assert is_scalar("x")
    assert not is_scalar((1, 2))
    assert not is_scalar([1])


def test_transpose():
    assert transpose([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]
