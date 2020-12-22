import pytest
from ghp.objects import (Commit, Deploy, DeployStatus, Job, Log, LogLine,
                         Object, Pages, PagesBuild, Run, Step, rget)
from ghp.states import Progress, Status
from ghp.types import Sha, Date


def mkstub(**kwargs):
    """Return a Stub object"""
    klass = kwargs.get("klass")
    class Stub(): ...
    if klass:
        Stub.__name__ = f"{klass}Stub"
    obj = Stub()
    for k,v in kwargs.items():
        setattr(obj, k, v)
    return obj


def mkclass(fields={}, name="TestObject"):
    """Make a Object subclass"""
    class TestObject(Object):
        @property
        def fields(self):
            return fields
    TestObject.__name__ = name
    return TestObject


def test_fields_mapping():
    """Object.__init__ extracts values according to Object.fields and
       Object.__repr__ includes values as specified in Object.fields"""

    klass = mkclass(dict(
        id=("id", True),
        author=("author.name", False),
        letters=("letters", False, list)
    ))
    t = klass({'id': 10, 'author': {'name': "X"}, 'letters': "abc"})

    assert repr(t) == "TestObject({'id': 10})"
    assert t.author == "X"
    assert t.id == 10
    assert t.letters == ["a", "b", "c"]


def test_states():
    """Object.states returns a generator of all defined attrs progress, status"""
    klass= mkclass()

    t = klass()
    assert list(t.states) == []

    t = klass()
    t.status = Status.queued
    assert list(t.states) == [t.status]

    t = klass()
    t.progress = Progress.in_progress
    assert list(t.states) == [t.progress]

    t = klass()
    t.status = Status.queued
    t.progress = Progress.in_progress
    assert sorted(list(t.states)) == sorted([t.progress, t.status])


def test_is_ok():
    """Object.is_ok returns True if all states are Ok.ok"""
    klass= mkclass()

    t = klass()
    assert t.is_ok, "is_ok is True if neither status nor progress is defined"

    t = klass()
    t.status = Status.success
    assert t.is_ok, \
        "is_ok is True if status.ok is True and no progress is defined"

    t = klass()
    t.status = Status.queued
    assert not t.is_ok, \
        "is_ok is False if status.ok is False and no progress is defined"

    t = klass()
    t.progress = Progress.completed
    assert t.is_ok, \
        "is_ok is True if progress.ok is True and no status is defined"

    t = klass()
    t.progress = Progress.in_progress
    assert not t.is_ok, \
        "is_ok is False if progress.ok is False and no status is defined"

    t = klass()
    t.status = Status.queued
    t.progress = Progress.in_progress
    assert not t.is_ok, \
        "is_ok is False if in_progress.ok and progress.ok are both False"

    t = klass()
    t.status = Status.success
    t.progress = Progress.in_progress
    assert not t.is_ok, \
        "is_ok is False if status.ok and progress.ok are both False"

    t = klass()
    t.status = Status.success
    t.progress = Progress.in_progress
    assert not t.is_ok, \
        "is_ok is False if status.ok is False and progress.ok is True"

    t = klass()
    t.status = Status.queued
    t.progress = Progress.completed
    assert not t.is_ok, \
        "is_ok is False if status.ok is False and progress.ok is True"

    t = klass()
    t.status = Status.success
    t.progress = Progress.completed
    assert t.is_ok, \
        "is_ok is True if status.ok and progress.ok are both True"


def test_is_open():
    """is_open returns True if any states None or Ok.busy"""
    klass= mkclass()

    t = klass()
    assert not t.is_open, "is_open is False if states is empty"

    t = klass()
    t.status = None
    assert t.is_open, "is_open is True if any states are None"

    t = klass()
    t.status = Status.queued
    assert t.is_open, "is_open is True if any states are Ok.busy"

    t = klass()
    t.progress = Progress.in_progress
    assert t.is_open, "is_open is True if any states are Ok.busy"

    t = klass()
    t.status = Status.success
    t.progress = Progress.in_progress
    assert t.is_open, "is_open is True states include Ok.busy"

    t = klass()
    t.status = Status.success
    t.progress = Progress.completed
    assert not t.is_open, "is_open is False if all states are not Ok.busy"


def test_commit():
    """Test Commit Objects"""
    data = {
        'sha': "0fd4c7e39a8b47cda54fd813922dca90711c0ea9",
        'stats': {
            'total': 0,
            'additions': 0,
            'deletions': 0},
        'files': [],
        'commit': {
            'tree': {"sha": "35d7b5a5582bfe55171e831f5c553134fe2f3c6e"},
            'message': "Update documentation",
            'committer': {
                'name': "Jane Doe"},
            'author': {
                'name': "John Doe",
                "date": "2020-11-27T12:46:21Z",
            },
        },
    }
    t = Commit(data)

    assert isinstance(t.sha, Sha)
    assert t.sha == data['sha']
    assert isinstance(t.tree, Sha)
    assert t.tree == data['commit']['tree']['sha']
    assert t.stats == data['stats']
    assert t.files == data['files']
    assert t.body == data['commit']['message']
    assert t.message == data['commit']['message']
    assert t.author == data['commit']['author']['name']
    assert t.committer == data['commit']['committer']['name']
    assert repr(t) == "Commit({'sha': '0fd4c7e', 'date': Date(2020-11-27), 'author': 'John Doe'})"


@pytest.mark.skip(reason="broken")
def test_deploy():
    #  id=("id", True),
    #  sha=("sha", True, Sha),
    #  date=("created_at", True, Date),
    #  creator=("creator.login", False),
    #  status=(None, True, Status),
    #  master_sha=(None, True, Sha),

    # commit, message, master_sha, status, deploy_status_list


    data = {
        'id': 302389563,
        'sha': "0fd4c7e39a8b47cda54fd813922dca90711c0ea9",
        'created_at': "2020-12-16T08:55:50Z",
        'creator': {"login": "github-pages[bot]"},
    }
    message = "Update documentation"
    commit = mkstub(body=message, message=message, klass="Commit")
    deploy_status = mkstub(status="success", klass="DeployStatus")
    deploy_status_request = mkstub( klass="DeployStatusRequest")
    deploy_status_request.data = [deploy_status]
    deploy_status_list = [deploy_status_request]
    deploy_status_list_request = mkstub(
        data=deploy_status_list,
        klass="DeployStatusListRequest")

    t = Deploy(data)
    t.commit_request = mkstub(data=commit, klass="CommitRequest")
    t.deploy_status_list_request = deploy_status_list_request

    assert isinstance(t.sha, Sha)
    assert t.sha == data['sha']
    assert isinstance(t.date, Date)
    assert t.creator == data['creator']['login']
    assert t.message == message
    assert t.commit == commit
    assert not t.master_sha
    assert t.deploy_status_list_request == deploy_status_list_request
    assert t.deploy_status_list == deploy_status_list
    assert t.deploy_status.__class__.__name__ == deploy_status.__class__.__name__
    assert t.deploy_status == deploy_status
    #  assert t.status == deploy_status.status

    #  assert t.deploy_status == deploy_status, \
    #      f"t.deploy_status: {t.deploy_status.__class__.__name__}, deploy_status: {t.deploy_status.__class__.__name__}"
    #  assert isinstance(t.deploy_status, Status)
    # assert t.status is status


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


def test_rget():
    """rget(source, keys) gets a value from a nested dict"""
    org = {'ops': { 'manager': "Joe Smith"}, 'manager': "Bill Jones"}
    assert rget(org, "manager") == 'Bill Jones'

    assert rget(org, "ops.manager") == 'Joe Smith'
