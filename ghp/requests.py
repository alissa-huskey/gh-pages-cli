"""Requests module -- Classes for making requests to the Github API"""

from abc import ABC, abstractmethod
from functools import cached_property
import json

from . import DATA_DIR
from .app import App
from .objects import (Commit, Deploy, DeployStatus, Job, Log, LogLine, Pages,
                      PagesBuild, Run, Step)
from .types import Sha


__all__ = [
    "CommitRequest",
    "DeploysRequest",
    "JobLogRequest",
    "JobsRequest",
    "PagesRequest",
    "PagesBuildsRequest",
    "RunsRequest",
    "StatusRequest",
]


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


class DeploysRequest(Request, Additive):
    """Class for requesting a list of deployments.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#deployments
    """

    dirname: str = "deploys"

    def mkdeploy(self, data):
        """Returns a Deploy object for data"""
        deploy = Deploy(data)
        deploy.statuses_request = StatusRequest(deploy)
        deploy.commit_request = CommitRequest(deploy.sha)
        return deploy

    @property
    def data(self):
        """Returns a list of Deploy objects."""
        return [ self.mkdeploy(x) for x in self.request_data ]

    @property
    def endpoint(self):
        """deployments endpoint"""
        return "deployments"


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


class RunsRequest(Request, Additive):
    """Class for requesting a list workflow runs.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/actions#workflow-runs
    """

    dirname: str = "runs"

    def mkrun(self, data):
        """Create a Run object for data"""
        run = Run(data)
        run.jobs_request = JobsRequest(run)
        return run

    @property
    def data(self):
        """Returns a list of Run objects."""
        return [ self.mkrun(x) for x in self.request_data["workflow_runs"] ]

    @property
    def endpoint(self):
        """Runs endpoint."""
        return "actions/runs"


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
