"""App module"""

from functools import cached_property
from typing import Any
from itertools import chain

from blessed.terminal import Terminal
from click import style
import click
from more_itertools import always_iterable

from .states import Ok


__all__ = ["App"]


class App():
    """Class for the top level app."""

    """Application object"""
    APP: Any

    def __init__(self, local=False, refresh=False, verbose=False,):
        """Initializer
           Set option attrubites and print messages about enabled options.
        """
        self.__class__.APP = self

        self.term = Terminal()
        self.writer = Writer()
        self.width, self.height = click.get_terminal_size()
        self.force_local = local
        self.refresh = refresh
        self.verbose = verbose

        if self.force_local and self.refresh:
            abort("--local and --refresh are exclusive")

        self.msg(self.style.mode("verbose", self.verbose))
        self.msg(self.style.mode("local", self.force_local))
        self.msg(self.style.mode("refresh", self.refresh))

    def msg(self, *args):
        """Print user message"""
        # don't print empty args
        if not [a for a in args if a]:
            return

        print(style(">", fg="cyan"), *args)

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
            line.append(f"{colorful.yellow}{prefix:<12}{colorful.reset}:")
        print(*line, *args, file=stderr)

    def abort(self, *args):
        """Print an error message and exit with status code 1"""
        print(colorful.red("Error"), *args, file=stderr)
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
            return f"{name.capitalize()} mode enabled."

    def step(self, step, width=2) -> str:
        """Format a job step"""
        num, desc = "-", "-"
        if step:
            num, desc = step.number, step.desc[0:20]
        return f"{num:>{width}} {desc}"


