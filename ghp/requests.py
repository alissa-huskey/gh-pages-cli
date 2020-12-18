"""Requests module -- Classes for making requests to the Github API"""

from abc import ABC, abstractmethod
from datetime import datetime
from functools import cached_property
import json
from subprocess import run as shell_run

import requests

from .app import App
from .downloadable import Dynamic, Finite, Additive, Static
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

class RequestError():
    def __init__(self, response):
        """Initializer"""
        data = response.json()
        self.code = response.status_code
        self.reason = response.reason
        self.message = data.get("message")
        self.docs = data.get("documentation_url")

class Request(ABC):
    """Abstract base class for requests to the Github API."""

    """Application object"""
    APP: App

    """Github API base URL"""
    BASE_URL: str = "https://api.github.com"

    """Github API Version"""
    API_VERSION: int = 3

    """Request type"""
    method: str = "GET"

    """Accept header media type"""
    media: str = "json"

    """Name of the directory under {App.data_dir} to store json files."""
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
        self.error = None
        self.response = None
        self.downloaded = False
        if not self.dirpath.is_dir():
          self.dirpath.mkdir(parents=True)
        self.get()

    def __repr__(self):
        """Return repr string containing endpoint"""
        return f"{self.__class__.__name__}({self.endpoint})"

    @cached_property
    def headers(self):
        """Request headers"""
        return {
            'Authorization': f"token {App.APP.token}",
            'Accept': f"application/vnd.github.v{self.API_VERSION}+{self.media}",
        }

    def get(self):
        """Load JSON data, making an API request to download if needed."""
        if self.exists():
            self.load()
        else:
            self.download()
            self.write()
        self.refresh()

    def refresh(self):
        """Download new data if needed"""
        if not self.should_refresh:
            return

        App.APP.msg("Refreshing", self.endpoint)
        self.download()
        self.store()
        self._filepath = self.default_filepath
        self.write()

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
           request type that follows {App.APP.repo}.

           For example, if the full endpoint for the class was:
           repos/{owner}/{repo}/commits/{ref}

           This method would return:
           f"commits/{ref}"
         """

    @cached_property
    def dirpath(self):
        """Returns a Path object to the directory where the json files for this
           API request type are stored."""
        return App.APP.data_dir.joinpath(self.dirname)

    def exists(self):
        """Return True if there are files downoaded for this request type."""
        return bool(self.files)

    @property
    def files(self):
        """List of json files for this API request type.
           Not cached, as it will need to be refreshed after a new file has
           been created using self.download().
        """
        files = [f for f in self.dirpath.glob("*.json") if f.stat().st_size]
        return sorted(files, reverse=True)

    @property
    def default_filepath(self):
        """Returns a Path object to the file to create."""
        return self.dirpath.joinpath(f"{self.today}.json")

    @property
    def filepath(self):
        """Return a Path object to either an existing file or the file to
           create."""
        if "_filepath" not in self.__dict__:
            if self.files:
                self._filepath = self.files[0]
            else:
                self._filepath = self.default_filepath
        return self._filepath

    @filepath.setter
    def filepath(self, value):
        """self.filepath setter"""
        self._filepath = value

    def load(self):
        """Load self.request_data from the self.filepath"""
        if not self.filepath.is_file():
          return

        with self.filepath.open() as fp:
          self.request_data = json.load(fp)

    @property
    def url(self):
        """Github API full url"""
        return f"{self.BASE_URL}/repos/{App.APP.repo}/{self.endpoint}"

    def request(self):
        """Make Github API request"""
        App.APP.info(self.endpoint, prefix=f"{self.__class__.__name__} requesting")
        self.response = requests.request(self.method, self.url, headers=self.headers)
        if not self.response.ok:
            self.error = RequestError(self.response)
            return

    def store(self):
        """Save self.request_data"""
        self.request_data = self.response.json()

    def download(self):
        """Make a request to the Github API and store results to
           self.request_data
        """
        self.request()
        self.store()

    def write(self):
        """Write self.request_data json file."""
        App.APP.info(self.filepath, prefix="Writing file")
        with self.filepath.open("w") as fp:
          json.dump(self.request_data, fp, indent=2)

    @cached_property
    def today(self):
        """Return date string formatted for filename"""
        return datetime.today().strftime("%Y-%m-%d-%s")


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
    endpoint: str = "deployments"

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


class PagesRequest(Request, Dynamic):
    """Class for github pages requests.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#pages
    """
    dirname: str = "pages"
    endpoint: str = "pages"

    @property
    def data(self):
        """Returns a Pages object."""
        return Pages(self.request_data)


class JobLogRequest(ChildRequest, Finite):
    """Class for requesting job logs
       https://docs.github.com/en/free-pro-team@latest/rest/reference/actions#download-job-logs-for-a-workflow-run
    """

    dirname: str = "logs"
    media: str = "raw"

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

    def write(self):
        """Write self.request_data log file."""
        with self.filepath.open("w", encoding="ascii") as fp:
            fp.write(self.request_data)

    def store(self):
        """Save self.request_data"""
        self.request_data = self.response.text.splitlines()

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

    def mklog(self, data):
        """Return a Job object for data"""
        job = Job(data, self.parent)
        job.log_request = JobLogRequest(job)
        return job

    @property
    def data(self):
        """Set data to a list of Job objects."""
        return [ self.mklog(x) for x in self.request_data["jobs"] ]

    @property
    def endpoint(self):
        """The job runs endpoint."""
        return f"actions/runs/{self.parent.id}/jobs"


class PagesBuildsRequest(Request, Additive):
    """Class for requesting a list of Github Pages builds.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#list-github-pages-builds
    """

    dirname: str = "builds"
    endpoint: str = "pages/builds"

    @property
    def data(self):
        """Returns a list of Deploy objects."""
        return [ PagesBuild(x) for x in self.request_data ]


class RunsRequest(Request, Additive):
    """Class for requesting a list workflow runs.
       https://docs.github.com/en/free-pro-team@latest/rest/reference/actions#workflow-runs
    """

    dirname: str = "runs"
    endpoint: str = "actions/runs"

    def mkrun(self, data):
        """Create a Run object for data"""
        run = Run(data)
        run.jobs_request = JobsRequest(run)
        return run

    @property
    def data(self):
        """Returns a list of Run objects."""
        return [ self.mkrun(x) for x in self.request_data["workflow_runs"] ]


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
        """API endpoint following App.repo"""
        return f"deployments/{self.parent.id}/statuses"
