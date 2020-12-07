import pytest
from ghp.objects import (Commit, Deploy, DeployStatus, Job, Log, LogLine,
                         Pages, PagesBuild, Run, Step)


@pytest.mark.skip(reason="todo")
def test_fields_mapping():
    ...


@pytest.mark.skip(reason="todo")
def test_states():
    ...


@pytest.mark.skip(reason="todo")
def test_is_ok():
    ...


@pytest.mark.skip(reason="todo")
def test_is_open():
    ...


@pytest.mark.skip(reason="todo")
def test_commit():
    # commit.message
    ...


@pytest.mark.skip(reason="todo")
def test_deploy():
    # commit, message, master_sha, status, statuses
    ...


@pytest.mark.skip(reason="todo")
def test_commit():
    ...


@pytest.mark.skip(reason="todo")
def test_deploy_status():
    ...


@pytest.mark.skip(reason="todo")
def test_job():
    # steps, last_step, url, log_request, log
    ...


@pytest.mark.skip(reason="todo")
def test_log():
    # lines, is_open, filter, errors, belongs_to
    ...


@pytest.mark.skip(reason="todo")
def test_log_line():
    # eq, lt, parse
    ...


@pytest.mark.skip(reason="todo")
def test_pages():
    ...


@pytest.mark.skip(reason="todo")
def test_pages_build():
    # id, message_parts, more_info, error, commit_request, commit
    ...


@pytest.mark.skip(reason="todo")
def test_run():
    # jobs, last_job, find_build, find_deploy
    ...


@pytest.mark.skip(reason="todo")
def test_step():
    ...


@pytest.mark.skip(reason="todo")
def test_rget():
    ...
