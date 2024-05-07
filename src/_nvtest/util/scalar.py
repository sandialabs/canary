"""Simple classes that subclass Python's builtin float, int, and str classes.
These classes are used when reading vvtest .vvt files so that a 'string'
property can be added and later used to create test case execution directories"""


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
