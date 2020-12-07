"""Package init file"""

from datetime import datetime
from pathlib import Path


__version__ = '0.1.0'
__all__ = ["TODAY"]

TODAY = datetime.today().strftime("%Y-%m-%d-%s")
