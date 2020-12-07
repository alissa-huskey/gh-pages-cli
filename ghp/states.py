"""States module -- enum classes for representing states"""

from enum import Enum, IntEnum


__all__ = [
    "BuildStatus",
    "Ok",
    "Progress",
    "Status",
]


class Ok(IntEnum):
    """Simplified statuses, """
    busy   =  0  # pending, queued, in-progress
    ok     =  1  # success, built, completed
    fail   = -1  # error, failure
    error  = -2  # invalid state name

    def __bool__(self):
        """Return True for truthy Ok status"""
        return self.value > 0


# error, failure, pending, in_progress, queued, or success
# queued, in_progress, or completed.
# success, failure, neutral, cancelled, skipped, timed_out, or action_require
class AbstractState(bytes, Enum):
    """Abstract class for state-like Enum objects.
       Provides instanciation by name and an abstract ok() method.
    """

    def __new__(cls, value, is_ok: Ok=None):
        """Initialize value and optional is_ok Ok object"""
        obj = bytes.__new__(cls, [value])
        obj._value_ = value
        obj.ok = is_ok
        return obj

    @classmethod
    def _missing_(cls, value):
        """Allow instantiation by case-insenstive name"""
        matches = [match for name, match in cls.__members__.items()
                    if name.lower() == value.lower()]
        if matches:
            return matches[0]
        super()._missing_(value)


class Progress(AbstractState):
    """Class for progress statuses."""
    queued       = (1, Ok.busy)
    in_progress  = (2, Ok.busy)
    completed    = (3, Ok.ok)


class BuildStatus(AbstractState):
    """Class for build statuses.
       Used for Gihub Pages.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#pages
    """
    null      = (1, Ok.busy)
    queued    = (2, Ok.busy)
    building  = (3, Ok.busy)
    built     = (4, Ok.ok)
    errored   = (5, Ok.fail)


class Status(AbstractState):
    """Class for success statuses.
       Used for deploy statuses, probably workflow jobs.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#deployments
    """
    error        = (1, Ok.fail)
    failure      = (2, Ok.fail)
    pending      = (3, Ok.busy)
    in_progress  = (4, Ok.busy)
    queued       = (5, Ok.busy)
    success      = (6, Ok.ok)

