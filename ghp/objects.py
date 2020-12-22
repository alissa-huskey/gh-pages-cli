"""Objects module -- classes for data received from the Github API"""

from abc import ABC, abstractmethod
from functools import cached_property
import re

from more_itertools import first, last

from .app import App
from .states import BuildStatus, Ok, Progress, Status
from .types import Date, Missing, Sha


__all__ = [
    "Commit",
    "Deploy",
    "DeployStatus",
    "Job",
    "Log",
    "LogLine",
    "Pages",
    "PagesBuild",
    "Run",
    "Step",
]


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

    def __init__(self, data: dict = {}):
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

    def __init__(self, parent, data: dict = {}):
        """Initializer
           Assigns self.parent

           Params
           ------
           data: (dict) the Json data received from GitHub
           parent: (Object) the parent object
        """
        super().__init__(data)
        self.parent = parent


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
        return [Step(self, x) for x in self.request_data["steps"]]

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
        return f"https://github.com/{App.APP.repo}/runs/{self.id}?check_suite_focus=true"

    @cached_property
    def log(self):
        """Return the Log object for this Job"""
        return self.log_request.data


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
