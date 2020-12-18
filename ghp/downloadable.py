"""Downloadable mixin classes

Mixin classes to provide the should_refresh method.
"""

from abc import ABC, abstractmethod

from .app import App

__all__ = ["Dyanmic", "Finite", "Additive", "Static"]

class Downloadable():
    """Psudo-abstract base class to provide should_refresh method."""

    @property
    @abstractmethod
    def should_refresh(self):
        """Return True if the file for this particular request should be
        refreshed."""
        raise Exception("should_download() should be defined in inherting classes.")


class Dynamic(Downloadable):
    """For requests that respond with data that is a snapshot in time."""

    @property
    def should_refresh(self):
        """True if --refresh unless just downloaded"""
        return not self.downloaded and App.APP.refresh


class Finite(Downloadable):
    """For requests that respond with data for a single object which may be
       modified until it is closed."""

    @property
    def should_refresh(self):
        """True for open objects unless --local or just downloaded"""
        if App.APP.force_local or self.downloaded:
            return False

        return self.is_open


class Additive(Downloadable):
    """For requests that respond with a list of Finite objects which may be
       added to."""

    @property
    def should_refresh(self):
        """True if --refresh or if any member objects are open, unless --local
           or just downloaded."""
        if App.APP.force_local or self.downloaded:
            return False

        return self.is_open or App.APP.refresh


class Static(Downloadable):
    """For requests that do not change once downloaded."""

    @property
    def should_refresh(self):
        """Never refresh."""
        return False
