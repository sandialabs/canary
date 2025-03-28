# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


class Singleton:
    """Simple wrapper for lazily initialized singleton objects."""

    def __init__(self, factory):
        """Create a new singleton to be initiated with the factory function.

        Args:
            factory (function): function taking no arguments that
                creates the singleton instance.
        """
        self.factory = factory
        self._instance = None

    @property
    def instance(self):
        if self._instance is None:
            self._instance = self.factory()
        return self._instance

    def __getattr__(self, name):
        # When unpickling Singleton objects, the 'instance' attribute may be
        # requested but not yet set. The final 'getattr' line here requires
        # 'instance'/'_instance' to be defined or it will enter an infinite
        # loop, so protect against that here.
        if name in ["_instance", "instance"]:
            raise AttributeError()
        return getattr(self.instance, name)

    def __getitem__(self, name):
        return self.instance[name]

    def __contains__(self, element):
        return element in self.instance

    def __call__(self, *args, **kwargs):
        return self.instance(*args, **kwargs)

    def __iter__(self):
        return iter(self.instance)

    def __str__(self):
        return str(self.instance)

    def __repr__(self):
        return repr(self.instance)
