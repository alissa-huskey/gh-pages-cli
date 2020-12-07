"""App module"""

from functools import cached_property
from itertools import chain
from pathlib import Path
import re
from subprocess import run as shell_run
from sys import stderr
from typing import Any

from blessed.terminal import Terminal
import click
from click import style
from more_itertools import always_iterable

from .states import Ok


__all__ = ["App"]


class App():
    """Class for the top level app."""

    """Application object"""
    APP: Any

    def __init__(self, repo=None, data_root=None, local=False, refresh=False, verbose=False):
        """Initializer
           Set option attrubites and print messages about enabled options.
        """
        # set attrs from options
        self.data_root = data_root
        self.repo = repo
        self.force_local = local
        self.refresh = refresh
        self.verbose = verbose

        # validate options
        if self.force_local and self.refresh:
            self.abort("The --local and --refresh flags are mutually exclusive.")

        # set globals
        self.__class__.APP = self
        self.term = Terminal()
        self.writer = Writer()
        self.width, self.height = click.get_terminal_size()

        # user messages
        self.info(self.repo, prefix="Repo")
        self.msg(self.style.mode("verbose", self.verbose))
        self.msg(self.style.mode("local", self.force_local))
        self.msg(self.style.mode("refresh", self.refresh))

    @property
    def repo(self):
        """Return _repo"""
        return self._repo

    @repo.setter
    def repo(self, value: str):
        """Set _repo. default: parse from url of origin remote
        accepts strings like:
            - alissa-huskey/python-class
            - https://github.com/mgutz/ansi
            - git@github.com:alissa-huskey/gh-pages-cli.git
            - https://github.com/bats-core/bats-core.git
        """
        # get the default value from remote origin url in current dir
        if not value:
            res = shell_run(["git", "remote", "get-url", "origin"],
                              capture_output=True)
            if res.returncode != 0:
                return
            value = res.stdout.decode().strip()

        # remove trailing .git
        if value.endswith(".git"):
            value = value[:-4]

        # parse repo from full URI
        if match := re.search(r"github.com[/:](?P<repo>.+)$", value):
            value = match.group("repo")

        if not value:
            self.abort("Repo is not set, and unable to get from git.\n"
                       "      Please set GHP_REPO env var or use the --repo flag.")

        self._repo = value

    @property
    def data_root(self):
        """Return _data_root"""
        return self._data_root

    @data_root.setter
    def data_root(self, value):
        """Set _data_root to Path object, default ~/.ghp"""
        if value:
            value = Path(value).resolve()
        if not value:
            value = Path.home().joinpath(".ghp")

        if not value.parent and value.parent.is_dir():
            abort(f"Invalid path to data_root: {value}")

        self._data_root = value

    @property
    def data_dir(self):
        """Return a Path object to the data dir for this repo"""
        data_dir = self.data_root.joinpath(*self.repo.split("/"))
        return data_dir

    def msg(self, *args):
        """Print user message"""
        # don't print empty args
        if not [a for a in args if a]:
            return

        text = " ".join(args)
        print(style(">", fg="cyan"), style(text, fg="bright_black", bold=False))

    def info(self, *args, multi=False, prefix=None):
        """Print info message if in verbose mode.

           Params
           ------
           *args (Any): to be printed
           prefix  (str, default=None): prefix string, will be highlighted in output
           multi (bool, default=False):
              - if True:  treat each arg as an individual info() call
              - if False: pass *args to print() to be " " joined
        """
        if not self.verbose: return

        if multi:
            for i,a in enumerate(args):
                prefix = prefix or ""
                self.info(a, prefix=f"{prefix}[{i}]")
            return

        line = [style("[Info]", fg="cyan")]
        if prefix:
            line.append(style("{:<12}".format(prefix), fg="yellow"))

        text = style(" ".join(args), fg="bright_black")
        print(*line, text, file=stderr)

    def abort(self, *args):
        """Print an error message and exit with status code 1"""
        print(style("Error", fg="red"), *args, file=stderr)
        exit(1)

    @cached_property
    def style(self):
        """Return Style object"""
        return Style()


class Writer():
    """Writer class to manage indentation and keep a buffer of text to print."""

    """Number of spaces to increment per indentation level."""
    INDENT_INCR: int = 2

    def __init__(self):
        """Intitialize attrs"""
        self.buf = []
        self.level = 0
        self.indentation = None

    @property
    def indentation(self):
        """(str) The literal spaces that make up the current indentation.
           Can be set to override the current indentation level.

        Returns either:
            - the value of _indentation if set
            - or the computed value from self.level
        """

        if self._indentation:
            return self._indentation
        return " " * self.INDENT_INCR * self.level

    @indentation.setter
    def indentation(self, value):
        """Indentation setter"""
        self._indentation = value

    def indent(self, level:int =1, to:int =None):
        """Add to either the current indentation level, or set the specific
           number of spaces.
        Params
        ------
        level (int, default=1)   : Number of levels to add to the current indentation level
        to    (int, default=None): Number of spaces to indent to
        """
        if to:
            self.indentation = " " * to
            return
        self.level += level

    def dedent(self, level: int=1, reset=False, clear=False, zero=False):
        """Reduce or zero out the current level of indentation, and/or clear
           the current value of self.indentation.
        Params
        ------
        level (int,  default=1)    : Number to remove from current indentation level
        zero  (bool, default=False): Set the current indentation level to zero
        clear (bool, default=False): Clear indentation value
        reset (bool, default=False): same as zero and clear
        """
        self.level -= level
        if clear or reset:
            self.indentation = None
        if zero or reset:
            self.level = 0

    def add(self, *args, sep=""):
        """Add to the buffer.
        Params
        ------
        - *args                    : text to be added
        -  sep (str, default="")   : inserted between args
        """
        self.buf.append(sep.join(args))

    def add_line(self, *args, sep="", before=0, after=1, ensure=False):
        """Add indented line to the buffer.
        Params
        ------
        - *args                          : text to be added
        -  sep (str, default="")         : inserted between args
        -  before (int, default=0)       : number of newlines to prepend
        -  after (int, default=1)        : number of newlines to append
        -  ensure (bool, default=False)  : when True, append a newline only if missing from end
        """
        args = [self.indentation] + list(args)
        text = sep.join(args)

        if ensure and text.endswith("\n") and after > 0:
            after -= 1

        self.add("\n"*before, text, "\n"*after)

    def add_lines(self, lines, *args):
        """Add indented lines to the buffer.
        Examples
        --------
        >>> writer = Writer()
        >>> writer.add_lines(["one", "two", "three"])
        >>> writer.add_lines("one", "two", "three")
        """
        for line in chain(always_iterable(lines), args):
            self.add_line(line)

    def add_block(self, text):
        """Add a block of multiline text"""
        self.add_lines(text.splitlines())

    def paginate(self):
        """Output buffer with pagination."""
        click.echo_via_pager(self.buf, color=True)

    def print(self):
        """Print buffer."""
        for line in self.buf:
            print(line, end="")


class Style():
    """Class for styling output"""

    OK_SYMBOL     = "\u2714" # ✓
    FAIL_SYMBOL   = "\u2717" # ✗
    BUSY_SYMBOL   = "\u26AC" # ⚬
    ERROR_SYMBOL  = "\u26A0" # ⚠

    STATUS_STYLES = {
         Ok.busy:  (BUSY_SYMBOL,  "yellow"),
         Ok.ok:    (OK_SYMBOL,    "green"),
         Ok.fail:  (FAIL_SYMBOL,  "red"),
         Ok.error: (ERROR_SYMBOL, "red"),
    }

    def header(self, title, newlines=1):
        """Return a styled header"""
        title = style(title, bold=True)
        after = "\n"*newlines
        return f"\n{title}{after}"

    def status(self, obj):
        """Return a colored unicode symbol cooresponding to the Status object"""
        assert hasattr(obj, "ok"), f"Object {obj!r} has no property 'ok'."
        assert obj.ok in self.STATUS_STYLES, \
            f"Undefined STATUS_STYLES key for object {obj!r} with ok value {obj.ok}"

        symbol, color = self.STATUS_STYLES[obj.ok]
        return style(symbol, fg=color)

    def job(self, job) -> str:
        """Return a string that prints the job status symbol and last step info"""
        if not job:
            return "-"
        return f"{self.status(job)} {self.step(job.last_step)}"

    def mode(self, name, enabled) -> str:
        """Return message indicating a mode was enabled"""
        if enabled:
            return click.style(f"{name.capitalize()} mode enabled.",
                               fg="bright_black")

    def step(self, step, width=2) -> str:
        """Format a job step"""
        num, desc = "-", "-"
        if step:
            num, desc = step.number, step.desc[0:20]
        return f"{num:>{width}} {desc}"
