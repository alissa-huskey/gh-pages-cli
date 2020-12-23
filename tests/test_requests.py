from pathlib import Path

import pytest
import requests_mock

from ghp.requests import (CommitRequest, DeploysRequest, JobLogRequest,
                          JobsRequest, PagesRequest, PagesBuildsRequest,
                          RunsRequest, StatusRequest)

DATADIR = Path(__file__).parent.joinpath("data")


@pytest.mark.skip(reason="todo")
def test_commit_request():
    ...


@pytest.mark.skip(reason="todo")
def test_deploy_request():
    ...


@pytest.mark.skip(reason="todo")
def test_job_log_request():
    ...


@pytest.mark.skip(reason="todo")
def test_jobs_request():
    ...


def test_pages_request():
    """Just experimenting with requests_mock for now"""
    f = DATADIR.joinpath("pages.json")
    with requests_mock.Mocker() as m:
        m.register_uri('GET', "https://api.github.com/repos/alissa-huskey/gh-pages-cli/pages", text=f.read_text())
        req = PagesRequest()
        req.download()
        assert req.request_data.get("is_mock")



@pytest.mark.skip(reason="todo")
def test_pages_builds_request():
    ...


@pytest.mark.skip(reason="todo")
def test_runs_request():
    ...


@pytest.mark.skip(reason="todo")
def test_status_request():
    ...
