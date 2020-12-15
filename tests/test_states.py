from ghp.states import Ok, BuildStatus, Progress, Status


def test_progress():
    assert Progress("queued").ok == Ok.busy
    assert Progress("in_progress").ok == Ok.busy
    assert Progress("completed").ok == Ok.ok


def test_build_status():
    assert BuildStatus("null").ok == Ok.busy
    assert BuildStatus("queued").ok == Ok.busy
    assert BuildStatus("building").ok == Ok.busy
    assert BuildStatus("built").ok == Ok.ok
    assert BuildStatus("errored").ok == Ok.fail


def test_status():
    assert Status("error").ok == Ok.fail
    assert Status("failure").ok == Ok.fail
    assert Status("pending").ok == Ok.busy
    assert Status("in_progress").ok == Ok.busy
    assert Status("queued").ok == Ok.busy
    assert Status("success").ok == Ok.ok


def test_status():
    assert Progress("queued").ok == Ok.busy
    assert Progress("in_progress").ok == Ok.busy
    assert Progress("completed").ok == Ok.ok


def test_ok():
    assert not Ok.busy
    assert not Ok.fail
    assert not Ok.error
    assert Ok.ok
