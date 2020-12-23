from sys import stderr
import pytest

class Stub():
    """Stub class"""
    def __new__(cls, **kwargs):
        """."""
        klass = kwargs.pop("klass", None)
        inst = super().__new__(cls)
        inst.__init__(**kwargs)
        if klass:
            inst.__name__ = klass

    def __init__(self, **kwargs):
        """."""
        for k,v in kwargs.items():
            setattr(self, k, v)

@pytest.fixture
def stub():
    return Stub
