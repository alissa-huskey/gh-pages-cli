"""Package init file"""

from datetime import datetime
from pathlib import Path


__version__ = '0.1.0'
__all__ = ["DATA_DIR", "ROOT_DIR", "SRC_DIR", "USER", "REPO"]

TODAY = datetime.today().strftime("%Y-%m-%d-%s")

ROOT_DIR = Path(__file__).absolute().parent.parent
SRC_DIR = ROOT_DIR.parent.joinpath("python-class")
DATA_DIR = SRC_DIR.joinpath("tmp", "github-data")

USER = "alissa-huskey"
REPO = "python-class"
