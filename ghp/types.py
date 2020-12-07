"""types module -- define some basic types"""

from datetime import datetime


__all__ = [
    "Date",
    "Missing",
    "Sha",
]


class Date(datetime):
    """Class for date strings"""

    """The format used by datetime.strptime() to parse date strings."""
    INPUT_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"

    def __new__(cls, *args):
        """Initialize like with a date string or like a datetime object.

        Examples
        --------
        >>> Date("2020-12-01T08:20:09Z")
        Date(2020-12-01)

        >>> Date(2020, 12, 1)
        Date(2020-12-01)
        """
        if isinstance(datestr := args[0], str):
            return super(Date, cls).strptime(datestr, cls.INPUT_FORMAT)
        else:
            return super().__new__(cls, *args)

    def __repr__(self):
        """Return repr string"""
        return f"Date({self})"

    def __str__(self):
        """Return the nicely formatted date string"""
        return str(self.date())


class Missing():
    """Class to indicate an item was not found.

       Examples
       --------
       >>> missing = Missing()
       >>> missing == None
       False
       >>> not missing
       True
    """

    def __bool__(self) -> bool:
        """Missing is falsy"""
        return False

    def __str__(self) -> str:
        """Return empty string"""
        return ""

    def __repr__(self) -> str:
        """Return string containing class name"""
        return "Missing()"


class Sha(str):
    """Class for git commit SHA strings
    Examples
    --------
    >>> sha = Sha("dfe4c0a60db827a8576bb510f99d574f9a42be4d")
    >>> str(sha)
    'dfe4c0a'
    >>> sha.full
    'dfe4c0a60db827a8576bb510f99d574f9a42be4d'
    """

    SHORT_LENGTH: int = 7

    def __new__(cls, content):
        """Return a string like object with an added `full` property containing
           the original 40-character sha string."""
        inst = str.__new__(cls, content)
        inst.full = content
        return inst

    def __repr__(self):
        """Provide trimmed sha string"""
        return repr(str(self))

    def __str__(self):
        """Provide trimmed sha string"""
        if len(self) <= self.SHORT_LENGTH:
          return self

        return self[0:self.SHORT_LENGTH]
