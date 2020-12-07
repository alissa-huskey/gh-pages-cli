#!/usr/bin/env python3

from subprocess import run as shell_run, CalledProcessError
from pathlib import Path
from pprint import pprint
from sys import stderr
from datetime import datetime
from functools import cached_property
from abc import ABC, abstractmethod
from enum import Enum, IntEnum
from typing import Any
from itertools import chain
import json
import re

from blessed.terminal import Terminal
import colorful
import click
from click import style
import tabulate as tabulate_module
from tabulate import tabulate
from more_itertools import first, last, always_iterable


TODAY = datetime.today().strftime("%Y-%m-%d-%s")

# TODO: ensure consistent deploy status naming
# TODO: replace Style class with templating
# TODO: Style.header() should work directly with Writer
# TODO: add --quiet flag and disable App.msg() messages
# TODO: Add --dry-run flag

# TODO: Consistent request.object, request.object_request, request.data naming
# TODO: request prod URL and check for <title>Python Class .*</title>
# TODO: Make this a legit module already
# TODO: Review color modules (colorama, colorful, blessed), remove unneeded

# TODO: Make these env vars/flags
# DATA_DIR = Path(__file__).absolute().parent.parent.joinpath("tmp", "github-data")
ROOT_DIR = Path(__file__).absolute().parent.parent
SRC_DIR = ROOT_DIR.parent.joinpath("python-class")
DATA_DIR = SRC_DIR.joinpath("tmp", "github-data")
# TODO: and/or parse from git config
#       git config remote.origin.url or ./.git/config
#       git remote get-url origin
#       remote.origin.url=git@github.com:alissa-huskey/python-class.git
USER = "alissa-huskey"
REPO = "python-class"


def rget(source, keys):
    """Get a value from nested dictionaries.
       Params
       ------
       * source (dict)   : (possibly) nested dictionary
       * keys (str, list): a string of nested keys seperated by "." or the
                           resulting list split from such a string
       Returns
       -------
       (Any) The final value

       Examples
       -------
       >>> org = {'ops': { 'manager': "Joe Smith"}, 'manager': "Bill Jones"}
       >>> rget(org, "manager")
       'Bill Jones'
       >>> rget(org, "ops.manager")
       'Joe Smith'
    """

    # Return None for empty keys
    if not keys or not source: return

    # split {keys} strings by "."
    if isinstance(keys, str):
        keys = keys.split(".")

    # get the first key from the list
    this_key = keys.pop(0)

    # recursively call rget() if there are keys remaining
    if len(keys):
        return rget(source.get(this_key, {}), keys)

    # if this was the last key, return the final value
    else:
        return source.get(this_key)


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


class Ok(IntEnum):
    """Simplified statuses, """
    busy   =  0  # pending, queued, in-progress
    ok     =  1  # success, built, completed
    fail   = -1  # error, failure
    error  = -2  # invalid state name


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


class Object(ABC):
    """Base class for objects created from the json data received from
       the github API."""

    """Application object"""
    APP: App

    """The data imported from the request."""
    request_data: dict

    def __repr__(self):
        """Return repr string containing values of attrs as defined in
           self.fields"""
        fields = { k: getattr(self, k) for
                   k,v in self.fields.items() if self.fields[k][1] }
        if fields:
            return f"{self.__class__.__name__}({fields!r})"
        else:
            return f"{self.__class__.__name__}()"

    def __init__(self, data: dict):
        """Initializer
           Extracts the values from the {data} dict as defined in by {self.fields}.

           Params
           ------
           data: (dict) the Json data received from GitHub
        """
        self.request_data = data
        for attr, mapping in self.fields.items():
            key = mapping[0]
            if not key:
              continue
            klass = mapping[2] if len(mapping) >= 3 else None
            val = rget(data, key)
            if klass and val:
              val = klass(val)
            setattr(self, attr, val)

    @property
    def states(self):
        """Return generator of all defined attrs progress, status"""
        return (getattr(self, attr)
                for attr in ("progress", "status")
                if hasattr(self, attr))

    @property
    def is_ok(self) -> bool:
        """Return True if all states are Ok.ok"""
        return all( (state and state.ok == Ok.ok for state in self.states) )

    @property
    def ok(self):
        """Return most problematic ok value of any defined and set states"""
        return min((state.ok for state in self.states if state))

    @property
    def is_open(self):
        """Return True if any states None or Ok.busy"""
        return any( (not state or state.ok == Ok.busy for state in self.states) )

    @property
    @abstractmethod
    def fields(self) -> dict:
        """Return a dict, where
            * key (str): object attribute to set
            * value (tuple):
                * (str) key to the cooresponding field from the JSON dict
                * (bool) if it should be included in the repr
                * (type, optional) type to instantiate attr as
        """


class ChildObject(Object):
    """Base class for objects that need to keep track of their parent object."""

    def __init__(self, data, parent):
        """Initializer
           Assigns self.parent

           Params
           ------
           data: (dict) the Json data received from GitHub
           parent: (Object) the parent object
        """
        super().__init__(data)
        self.parent = parent


class DeployStatus(Object):
    """Object class for the deploy status."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return {
            'id': ("id", True),
            'date': ("created_at", True, Date),
            'status': ("state", True, Status),
        }


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


class Run(Object):
    """Object class for workflow runs."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            id=("id", True),
            workflow_id=("workflow_id", False),
            number=("run_number", True),
            date=("created_at", True, Date),
            sha=("head_sha", False, Sha),
            job=("name", False),
            progress=("status", False, Progress),
            status=("conclusion", True, Status),
            branch=("head_branch", False),
            message=("head_commit.message", False),
        )

    def __init__(self, *args):
        """Initialize attrs"""
        super().__init__(*args)
        self.build = None
        self.deploy = None

    @cached_property
    def jobs(self):
        """Return a JobRequest."""
        return self.jobs_request.data

    @cached_property
    def jobs_request(self):
        """Return a JobRequest."""
        return JobsRequest(self)

    @property
    def last_job(self) -> str:
        """Return the last successful job or first failed job for this job"""
        if not self.jobs:
            return
        if not self.is_ok:
            failed = [job for job in self.jobs if not job.is_ok]
            return first(failed, None)
        return last(self.jobs, None)

    def find_build(self, builds: list) -> str:
        """Return Build object from list of {builds} with sha matching
           self.sha"""
        if not self.deploy:
            self.build = Missing()
            return

        res = [x for x in builds if x.sha == self.deploy.sha]
        self.build = first(res, Missing())
        return self.build

    def find_deploy(self, deploys: list) -> str:
        """Return Deploy object from list of {deploys} with master_sha matching
           self.sha"""
        res = [d for d in deploys if d.master_sha == self.sha]
        self.deploy = first(res, Missing())
        return self.deploy


class Step(ChildObject):
    """Object class for steps, child of Job."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            number=("number", True),
            status=("conclusion", True, Status),
            desc=("name", True),
        )


class PagesBuild(Object):
    """Object class for Github Pages build."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            id=(None, True),
            sha=("commit", True, Sha),
            date=("created_at", True, Date),
            status=("status", True, BuildStatus),
            message=("error.message", False),
            pushed_by=("pusher.login", False),
        )

    @cached_property
    def id(self):
        """Parse the build id from the `url` request_data field."""
        return last(self.request_data.get("url").split("/"))

    @cached_property
    def message_parts(self) -> tuple:
        """Return error message partitioned into (message, _, more_info_url)"""
        if not self.message:
            return
        sep = "For more information, see"
        parts = self.message.partition(sep)
        assert len(parts) == 3, \
            f"Failed to partiton error message:\nUsing: '{sep}'\n'Message: {self.message}'"
        return parts

    @cached_property
    def more_info(self) -> str:
        """Return more_info url from error message"""
        if not self.message:
            return
        return last(self.message_parts).strip()

    @cached_property
    def error(self) -> str:
        """Return error message"""
        if not self.message:
            return ""
        return first(self.message_parts).strip()

    @cached_property
    def commit_request(self):
        """Return CommitRequest object"""
        return CommitRequest(self.sha)

    @cached_property
    def commit(self):
        """Return Commit object"""
        return self.commit_request.data


class Pages(Object):
    """Object class for Github Pages info."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            url=("html_url", True),
            branch=("source.branch", True),
            path=("source.path", True),
            status=("status", True, BuildStatus),
        )


class Job(ChildObject):
    """Object class for jobs, child of Run."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            id=("id", True),
            progress=("status", False, Progress),
            status=("conclusion", False, Status),
            sha=("head_sha", True, Sha),
            name=("name", False),
            ok=(None, True),
        )

    @property
    def steps(self) -> list:
        """Return list of Step objects for this job"""
        return [Step(x, self) for x in self.request_data["steps"]]

    @property
    def last_step(self) -> str:
        """Return the last successful step or first failed step for this run"""
        if not self.steps:
            return
        if not self.is_ok:
            failed = (s for s in self.steps if not s.is_ok)
            return first(failed, self.steps[-1])
        return self.steps[-1]

    @property
    def url(self):
        """Return the URL to view the Job on github.com"""
        return f"https://github.com/{USER}/{REPO}/runs/{self.id}?check_suite_focus=true"

    @cached_property
    def log_request(self):
        """Return the JobLogRequest object for this job."""
        return JobLogRequest(self)

    @cached_property
    def log(self):
        """Return the Log object for this Job"""
        return self.log_request.data


class Commit(Object):
    """Class for commits."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            sha=("sha", True, Sha),
            date=("commit.author.date", True, Date),
            author=("commit.author.name", True),
            committer=("commit.committer.name", False),
            body=("commit.message", False),
            tree=("commit.tree.sha", False, Sha),
            stats=("stats", False),
            files=("files", False),
        )

    @property
    def message(self) -> str:
        """Return the first line of the commit message body"""
        return first(self.body.splitlines(), "")


class Deploy(Object):
    """Class for deploys."""

    @property
    def fields(self) -> dict:
        """Mapping of object attrs to (json field, include in repr, instance type)"""
        return dict(
            id=("id", True),
            sha=("sha", True, Sha),
            date=("created_at", True, Date),
            creator=("creator.login", False),
            status=(None, True, Status),
            master_sha=(None, True, Sha),
        )

    @cached_property
    def commit_request(self):
        """Return CommitRequest object"""
        return CommitRequest(self.sha)

    @cached_property
    def commit(self):
        """Return Commit object"""
        return self.commit_request.data

    @property
    def message(self):
        """Return commit.message without self.master_sha"""
        if not self.master_sha:
            return self.commit.message
        if end := self.commit.message.rfind(f" {self.master_sha.full}"):
            return self.commit.message[0:end]
        return self.commit.message

    @property
    def master_sha(self) -> str:
        """Returns a string with the sha from the master branch, parsed from the
            message of the deploy commit
        """
        if not self.commit.body:
            return
        sha = self.commit.body.split()[-1]
        if len(sha) == 40:
            return Sha(sha)

    @property
    def status(self) -> str:
        """Return Status object of first DeployStatus"""
        if not self.statuses:
            return
        return Status(self.statuses[0].status)

    @cached_property
    def statuses(self):
        """Returns list of Status objects"""
        return self.statuses_request.data

    @cached_property
    def statuses_request(self):
        """Returns a StatusRequest"""
        return StatusRequest(self)


class Downloadable():
    """Abstract base class to provide should_refresh method."""

    @property
    @abstractmethod
    def should_refresh(self):
        """Return True if this particular the file for this particular request
           should be re-downloaded."""
        raise Exception("Should be defined in inherting classes.")


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
    """For requests that respond with a list of Finite object which may be
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


class Request(ABC, Downloadable):
    """Abstract base class for requests to the Github API."""

    """Application object"""
    APP: App

    """Name of the directory under {DATA_DIR} to store json files."""
    dirname: str

    """The parsed data received from the Github API."""
    data: list

    """Indicates if the json file has been downloaded during this run."""
    downloaded: bool

    def __init__(self):
        """Initializer
           Create any missing directories and load JSON data, making an API
           request to download it first if needed.
        """
        self.downloaded = False
        if not self.dirpath.is_dir():
          self.dirpath.mkdir(parents=True)
        self.get()

    def __repr__(self):
        """Return repr string containing endpoint"""
        return f"{self.__class__.__name__}({self.endpoint})"

    def get(self):
        """Load JSON data, making an API request to download it first if
           needed.
        """
        if not self.exists():
            self.download()

        self.load()

        if self.should_refresh:
            App.APP.msg("Refreshing", self.endpoint)
            self.download()
            self.load()

    @property
    def is_open(self) -> bool:
        """Return True if any self.data objects are open"""
        if hasattr(self.data, "is_open"):
            return self.is_open
        else:
            return any((obj.is_open for obj in self.data))

    @property
    @abstractmethod
    def data(self):
        """Method to assign self.data to Object(s) created from request data.
           Params
           ------
           data: (dict, list) data received from the Github API request.
        """

    @property
    @abstractmethod
    def endpoint(self) -> str:
        """A string containing the part of the Github API endpoint for this
           request type that follows {REPO}.

           For example, if the full endpoint for the class was:
           /repos/{owner}/{repo}/commits/{ref}

           This method would return:
           f"commits/{ref}"
         """

    @cached_property
    def dirpath(self):
        """Returns a Path object to the directory where the json files for this
           API request type are stored."""
        return DATA_DIR.joinpath(self.dirname)

    def exists(self):
        """Return True if there are files downoaded for this request type."""
        return bool(self.files)

    @property
    def files(self):
        """List of json files for this API request type.
           Not cached, as it will need to be refreshed after a new file has
           been created using self.download().
        """
        files = list(self.dirpath.glob("*.json"))
        files.sort(reverse=True)
        return files

    @property
    def default_filepath(self):
        """Returns a Path object to the file to create."""
        return self.dirpath.joinpath(f"{TODAY}.json")

    @cached_property
    def filepath(self):
        """Returns a Path object to either an existing file or the file to
           create."""
        if self.files:
          return self.files[0]

        return self.default_filepath

    def load(self):
        """Load self.data from the most recent .json file in self.dirpath"""
        if not self.filepath.is_file():
          return

        with self.filepath.open() as fp:
          self.request_data = json.load(fp)

    def download(self):
        """Make a request to the Github API then save the resulting json file.
           Uses the `gh` CLI tool to avoid dealing with authentication.
           Raises CalledProcessError if the request fails.
        """
        result = shell_run(["gh", "api", f"/repos/{USER}/{REPO}/{self.endpoint}"],
                     capture_output=True)
        result.check_returncode()
        data = json.loads(result.stdout.decode())
        with self.filepath.open("w") as fp:
          json.dump(data, fp)


class ChildRequest(Request):
    """Base class for github requests that need to keep track of their parent
       object."""

    parent: None

    def __init__(self, parent):
        """Initializer
           Assigns self.parent.
        """
        self.parent = parent
        super().__init__()

    def exists(self):
        """Return True if there are files downoaded for this request type."""
        return self.filepath.is_file()

    @property
    def filepath(self):
        """Filename is the `{self.parent.id}.json`.'"""
        return self.dirpath.joinpath(f"{self.parent.id}.json")


class PagesRequest(Request, Dynamic):
    """Class for github pages requests.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#pages
    """
    dirname: str = "pages"

    @property
    def data(self):
        """Returns a Pages object."""
        return Pages(self.request_data)

    @property
    def endpoint(self):
        """API endpoint following REPO"""
        return "pages"


class StatusRequest(ChildRequest, Finite):
    """Class for deploy status requests.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#get-a-deployment-status
    """
    dirname: str = "statuses"

    @property
    def data(self):
        """Returns list of DeployStatus objects."""
        return [ DeployStatus(x) for x in self.request_data ]

    @property
    def endpoint(self):
        """API endpoint following REPO"""
        return f"deployments/{self.parent.id}/statuses"


class JobLogRequest(ChildRequest, Finite):
    """Class for requesting job logs
       https://docs.github.com/en/free-pro-team@latest/rest/reference/actions#download-job-logs-for-a-workflow-run
    """

    dirname: str = "logs"

    @property
    def endpoint(self):
        """The job logs endpoint."""
        return f"actions/jobs/{self.parent.id}/logs"

    @property
    def is_open(self):
        """Logs may be updated as if the parent job is updated."""
        return self.parent.is_open

    @cached_property
    def data(self):
        """Return Log object"""
        return Log(self.parent, self.request_data)

    def download(self):
        """Make a request to the Github API then save the resulting text file.
           Uses the `gh` CLI tool to avoid dealing with authentication.
           Raises CalledProcessError if the request fails.
        """
        with self.filepath.open("w") as fp:
            result = shell_run(
                ["gh", "api", f"/repos/{USER}/{REPO}/{self.endpoint}"],
                stdout=fp)
            result.check_returncode()

    @property
    def filepath(self):
        """Filename is the `{self.parent.id}.log`.'"""
        return super().filepath.with_suffix(".log")

    def load(self):
        """Read the logfile lines into self.request_data"""
        if not self.filepath.is_file():
          return
        with self.filepath.open() as fp:
            self.request_data = fp.readlines()


class LogLine():
    """Class to handle parsing and comparison of Log lines"""
    PATTERN = r"^(?P<date>[-0-9:.ZT]+)[ ]?(?:##\[(?P<cat>[a-z]+)\])?(?P<msg>.*)$"
    REGEX = re.compile(PATTERN)

    def __init__(self, num=0, text=""):
        """Initialize kwargs and parse."""
        self.num = num
        self.text = text
        self.parse()

    def __eq__(self, other):
        """Use line number and text for equivalence."""
        assert isinstance(other, self.__class__), \
            f"Unable to compare {self.__class__.__name__} and {other.__class__.__name__}"
        return (self.num, self.text) == (other.num, other.text)

    def __lt__(self, other):
        """Use line number for comparisons."""
        assert isinstance(other, self.__class__), \
            f"Unable to compare {self.__class__.__name__} and {other.__class__.__name__}"
        return self.num < other.num

    def parse(self, text=None):
        """Parse text of log line and assign to attributes date, category, msg.
           category is based on any text in ##[], defaulting to "normal" or
           "empty" if text contains only whitespace

        Params
        ------
        text (str, default=None): if present parse this instead of self.text

        Examples
        --------
        >>> l1 = "2020-12-01T08:20:01.7355988Z ##[section]Finishing: Request a runner to run this job"
        >>> l2 = "2020-12-01T08:20:09.6944852Z Current runner version: '2.274.2'"
        >>> l3 = "2020-12-01T08:20:43.8183495Z "
        >>> l4 = "\n"
        >>> line = LogLine()

        >>> line.parse(l1)
        >>> line.date
        '2020-12-01T08:20:01.7355988Z'
        >>> line.category
        'section'
        >>> line.msg
        'Finishing: Request a runner to run this job'

        >>> line.parse(l2)
        >>> line.date
        '2020-12-01T08:20:09.6944852Z'
        >>> line.category
        'normal'
        >>> line.msg
        "Current runner version: '2.274.2'"

        >>> line.parse(l3)
        >>> line.date
        '2020-12-01T08:20:43.8183495Z'
        >>> line.category
        'normal'
        >>> line.msg
        ''

        >>> line.parse(l4)
        >>> (line.category, line.date, line.msg)
        ('empty', None, None)
        """
        text = (text or self.text).strip()
        if not text:
            self.category, self.date, self.msg = "empty", None, None
            return

        match = self.REGEX.search(text)
        assert match, f"LogLine Unable to parse text #{self.num}:\n  '{text}'"
        self.date = match.group("date")
        self.category = match.group("cat") or "normal"
        self.msg = match.group("msg")


class Log():
    """Class for job Logs"""
    def __init__(self, parent, lines):
        """Initialize attrs"""
        self.parent = parent
        self.input_lines = lines

    @property
    def lines(self):
        """Return generator of LogLine objects"""
        return (LogLine(i+1, line) for i, line in enumerate(self.input_lines))

    @property
    def is_open(self):
        """True if parent Job is open"""
        return self.parent.is_open

    def filter(self, category, reverse=False):
        """Return filtered LogLine objects
        Params
        ------
        category (str)                 : category of lines to filter to
                                         (containing "##[{category}]")
        reversed (bool, default=False) : return reversed results
        """
        matches = (line for line in self.lines if line.category == category)
        if reverse:
            return sorted(matches, key=lambda l: l.num, reverse=True)
        return matches

    @cached_property
    def errors(self):
        """Return a generator yielding all error LogLines"""
        return self.filter("error")

    def belongs_to(self, child, category):
        """Returns the first {category} LogLine preceeding {child}.
        Params
        ------
        child (LogLine) : the LogLine in question
        category (str)  : the category of line to find
                          valid=["group", "section"]
        """
        assert category in ("group", "section"), \
            f"Argument 2, category, must be 'group' or 'section' not '{category}'"

        matches = (line for line in self.filter(category, reverse=True)
                   if line.num < child.num)
        return first(matches)


class JobsRequest(ChildRequest, Finite):
    """Class for requesting a list of workflow run jobs.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/actions#list-jobs-for-a-workflow-run
    """

    dirname: str = "jobs"

    @property
    def data(self):
        """Set data to a list of Job objects."""
        return [ Job(x, self.parent) for x in self.request_data["jobs"] ]

    @property
    def endpoint(self):
        """The job runs endpoint."""
        return f"actions/runs/{self.parent.id}/jobs"


class CommitRequest(Request, Static):
    """Class for requesting a commit.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#get-a-commit
    """

    dirname: str = "commits"

    def __init__(self, ref):
        """Initializer
           Assigns self.ref.
        """
        if isinstance(ref, Sha):
          ref = ref.full

        self.ref = ref
        super().__init__()

    @cached_property
    def filepath(self):
        """Filename uses {self.ref}"""
        return self.dirpath.joinpath(f"{self.ref}.json")

    def exists(self):
        """Return True if there are files downoaded for this request type."""
        return self.filepath.is_file()

    @property
    def data(self):
        """Return a Commit object."""
        return Commit(self.request_data)

    @property
    def endpoint(self):
        """deployments endpoint"""
        return f"commits/{self.ref}"


class PagesBuildsRequest(Request, Additive):
    """Class for requesting a list of Github Pages builds.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#list-github-pages-builds
    """

    dirname: str = "builds"

    @property
    def data(self):
        """Returns a list of Deploy objects."""
        return [ PagesBuild(x) for x in self.request_data ]

    @property
    def endpoint(self):
        """pages builds endpoint"""
        return "pages/builds"


class DeploysRequest(Request, Additive):
    """Class for requesting a list of deployments.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#deployments
    """

    dirname: str = "deploys"

    @property
    def data(self):
        """Returns a list of Deploy objects."""
        return [ Deploy(x) for x in self.request_data ]

    @property
    def endpoint(self):
        """deployments endpoint"""
        return "deployments"


class RunsRequest(Request, Additive):
    """Class for requesting a list workflow runs.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/actions#workflow-runs
    """

    dirname: str = "runs"

    @property
    def data(self):
        """Returns a list of Run objects."""
        return [ Run(x) for x in self.request_data["workflow_runs"] ]

    @property
    def endpoint(self):
        """Runs endpoint."""
        return "actions/runs"


def debug(app):
    """Print a bunch of debug info."""
    deploys = DeploysRequest()
    statuses = StatusRequest(deploys.data[0])
    runs = RunsRequest()
    run = runs.data[0]
    job = run.jobs[0]
    step = job.steps[0]
    commit_req = CommitRequest("dfe4c0a60db827a8576bb510f99d574f9a42be4d")
    commit = commit_req.data
    status = Status("success")
    progress = Progress("completed")
    builds = PagesBuildsRequest()
    build = builds.data[0]

    app.info(DATA_DIR, prefix="DATA_DIR")
    app.info(deploys.dirname, prefix="deploys.dirname")
    app.info(deploys.dirpath, prefix="deploys.dirpath")
    app.info(deploys.filepath, prefix="deploys.filepath")
    app.info(deploys.endpoint, prefix="deploys.endpoint")
    app.info(deploys.data[0], prefix="Deploy")

    app.info(statuses.dirname, prefix="statuses.dirname")
    app.info(statuses.dirpath, prefix="statuses.dirpath")
    app.info(statuses.filepath, prefix="statuses.filepath")
    app.info(statuses.endpoint, prefix="statuses.endpoint")
    app.info(statuses.data[0], prefix="DeployStatus")

    app.info(runs.dirname, prefix="runs.dirname")
    app.info(runs.dirpath, prefix="runs.dirpath")
    app.info(runs.filepath, prefix="runs.filepath")
    app.info(runs.endpoint, prefix="runs.endpoint")
    app.info(runs.data[0], prefix="Run")

    app.info( run.jobs_request.dirname, prefix="jobs.dirname")
    app.info( run.jobs_request.dirpath, prefix="jobs.dirpath")
    app.info(run.jobs_request.filepath, prefix="jobs.filepath")
    app.info(run.jobs_request.endpoint, prefix="jobs.endpoint")
    app.info(job, prefix="Job")

    app.info( run.jobs_request.dirname, prefix="jobs.dirname")
    app.info( run.jobs_request.dirpath, prefix="jobs.dirpath")
    app.info(run.jobs_request.filepath, prefix="jobs.filepath")
    app.info(run.jobs_request.endpoint, prefix="jobs.endpoint")
    app.info(step, prefix="Step")
    app.info(commit, prefix="Commit")
    app.info(Ok.ok, prefix="Ok")
    app.info(status, status.ok, prefix="Status")
    app.info(progress, progress.ok, prefix="Progress")
    app.info(build, prefix="Build")


def show_pages(obj):
    """Print the Github Pages details to buffer.
    Params
    ------
    obj (Pages): Pages object
    """
    app = App.APP
    rows = [
        [f"{app.style.status(obj.status)} {obj.url}"],
        [f"  branch: {obj.branch}, path: {obj.path}"],
    ]

    title = "Pages"
    table = tabulate(rows, tablefmt="rst").splitlines()
    app.writer.add_line(style(title, bold=True), "  ", table.pop(0), before=1)
    app.writer.indent(to=len(title)+2)
    app.writer.add_lines(table)
    app.writer.dedent(reset=True)


def show_deploys(deploys, count: int=3):
    """Print list of {count} recent deploys to buffer.
    Params
    ------
    deploys (List[Deploy]) : List of Deploy objects
    count (int)            : Max number to print
    """
    app = App.APP
    deploys_table = []
    for deploy in deploys[:count]:
        deploys_table.append({
            "OK": app.style.status(deploy.status),
            "date": deploy.date,
            "id": deploy.id,
            "commit": deploy.sha,
            "master": deploy.master_sha or " "*Sha.SHORT_LENGTH,
            "message": deploy.message[0:50],
        })

    app.writer.add_block(app.style.header("Repo Deploys"))
    app.writer.add_line()
    app.writer.indent()
    app.writer.add_block(tabulate(deploys_table, headers="keys"))
    app.writer.dedent(reset=True)


def show_runs(runs, deploys, builds, count: int=8):
    """Print the recent Github Action Workflow Runs to the buffer.
    Params
    ------
    runs (List[Run])       : List of workflow Run objects
    deploys (List[Deploy]) : List of repo Deploy objects
    """
    app = App.APP
    runs_table = []
    for run in runs[:count]:
        run.find_deploy(deploys)
        run.find_build(builds)


        runs_table.append({
            "#": run.number,
            "date": run.date,
            "id": run.id,
            "commit": run.sha,
            "message": run.message.splitlines()[0][0:30],
            "job": app.style.job(run.last_job),
            "deploy": f"{app.style.status(run.deploy.status)} {run.deploy.sha}" if run.deploy else "",
            "build": f"{app.style.status(run.build.status)} {run.build.id}" if run.build else "",
        })

    app.writer.add_block(app.style.header("Github Action Runs"))
    app.writer.add_line()
    app.writer.add_block(tabulate(runs_table, headers="keys"))


def show_builds(builds, count: int=3):
    """Print the recent Github Pages builds to the buffer.
    Params
    ------
    """
    app = App.APP
    table = []
    margin = len("  ✔     2020-12-05  219342206  2b45940   ") + 4
    wrap_width = app.width - margin

    for build in builds[:count]:
        table.append({
            "OK": app.style.status(build.status),
            "date": build.date,
            "id": build.id,
            "commit": build.sha,
            "message": build.commit.message,
        })

    app.writer.add_block(app.style.header("Github Pages Builds"))
    app.writer.add_line()
    app.writer.indent()
    app.writer.add_block(tabulate(table, headers="keys"))
    app.writer.dedent(reset=True)


def show_failed_job_errors(job):
    """Print the error messages if {job} failed.
    Params
    ------
    job (Job): workflow run Job object
    """
    if job.ok != Ok.fail:
        return

    app = App.APP
    margin = len(f"| 959 | section | {''} |") + 2
    wrap_width, idt = app.width - margin, " " * 2
    log = job.log
    table = []
    last_sec, last_group = LogLine(), LogLine()

    for err in log.errors:
        sec = log.belongs_to(err, "section")
        group = log.belongs_to(err, "group")

        if sec != last_sec:
            last_sec = sec
            table.append((sec.num, sec.category, f"{sec.msg} >"))

        if group != last_group:
            last_group = group
            table.append((group.num, group.category, f"{idt}{group.msg} >"))

        table.append((
            err.num, "error",
            click.wrap_text(
                f"- {err.msg}",
                width=wrap_width,
                initial_indent=(idt*3),
                subsequent_indent=idt*4,
                preserve_paragraphs=True
            )
        ))

    app.writer.add_block(app.style.header("Errors"))
    app.writer.indent()
    app.writer.add_block(tabulate(table, tablefmt="grid", colalign=("right",)))
    app.writer.dedent(reset=True)


def show_failed_build(build):
    """Print the stats and error message if {build} failed.
    Params
    ------
    build (Build): build object
    """
    if build.ok != Ok.fail:
        return

    app = App.APP
    app.info(build)

    ctx = click.get_current_context()

    table = [
        ("Build", f"[{style(build.status.name, fg='red')}] {build.date} {build.id}"),
        ("Error", build.error),
        ("More info", app.term.link(build.more_info, "Troubleshooting Github Pages Sites")),
    ]

    app.writer.add_block(app.style.header("\u2757 Last Build Failed"))
    app.writer.indent()
    app.writer.add_block(tabulate(table, tablefmt="rst"))
    app.writer.dedent(reset=True)


def show_failed_job(job):
    """Print the stats and error messages if {job} failed.
    Params
    ------
    job (Job): workflow run Job object
    """
    if job.ok != Ok.fail:
        return

    app = App.APP
    app.writer.add_block(app.style.header("\u2757 Last Run Failed"))
    show_failed_job_stats(job)
    show_failed_job_errors(job)


def show_failed_job_stats(job):
    """Print the stats if {job} failed.
    Params
    ------
    job (Job): workflow run Job object
    """
    if job.ok != Ok.fail:
        return

    minwidth = len("alissa-huskey/python-class > actions") + 2
    app = App.APP
    table = [
        ("Workflow", job.parent.workflow_id),
        ("Run", f"[{style(job.parent.status.name, fg='red')}] {job.parent.id}"),
        ("Job", f"[{style(job.status.name, fg='red')}] {job.id}"),
        ("Step", f"[{style(job.last_step.status.name, fg='red')}] {app.style.step(job.last_step, len(str(job.last_step.number)))}"),
        ("Log", str(job.log_request.filepath.relative_to(Path.cwd())).ljust(minwidth)),
        ("URL", app.term.link(job.url, f"{USER}/{REPO} > actions")),
    ]

    app.writer.indent()
    app.writer.add_block(tabulate(table, tablefmt="rst"))
    app.writer.dedent(reset=True)


@click.command()
@click.option("--local", "-l", is_flag=True, default=False,
              help="Don't download updates, even for pending states.'")
@click.option("--refresh", "-r", is_flag=True, default=False,
              help="Download updates.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Enable verbose mode.")
def main(**kwargs):
    """Show status information about Gihub Pages and Actions"""
    app = App(**kwargs)
    tabulate_module.PRESERVE_WHITESPACE = True
    #  debug(app)

    pages = PagesRequest()
    deploys = DeploysRequest()
    runs = RunsRequest()
    builds = PagesBuildsRequest()
    build = builds.data[0]

    show_pages(pages.data)
    show_runs(runs.data, deploys.data, builds.data)
    show_failed_job(runs.data[0].last_job)
    show_failed_build(build)

    app.writer.paginate()


if __name__ == "__main__":
    main()
