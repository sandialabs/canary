# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Simple classes that subclass Python's builtin float, int, and str classes.
These classes are used when reading vvtest .vvt files so that a 'string'
property can be added and later used to create test case execution directories"""

from .string import strip_quotes


class Float(float):
    @property
    def string(self) -> str:
        return self._string

    @string.setter
    def string(self, arg: str) -> None:
        self._string = arg


class Integer(int):
    @property
    def string(self) -> str:
        return self._string

    @string.setter
    def string(self, arg: str) -> None:
        self._string = arg


class String(str):
    @property
    def string(self) -> str:
        return self._string

    @string.setter
    def string(self, arg: str) -> None:
        self._string = arg


def cast(arg: str, type: str) -> Integer | Float | String:
    assert type in ("autotype", "str", "float", "int")
    x: Integer | Float | String
    if type == "str":
        x = String(strip_quotes(arg))
    elif type == "int":
        x = Integer(float(arg))
    elif type == "float":
        x = Float(arg)
    else:
        try:
            x = Integer(arg)
        except ValueError:
            try:
                x = Float(arg)
            except ValueError:
                x = String(arg)
    x.string = arg
    return x
