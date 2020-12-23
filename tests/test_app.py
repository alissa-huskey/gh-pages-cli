from pathlib import Path
from configparser import ConfigParser
from sys import stderr
from os import environ

import pytest

from ghp.app import App


ROOTDIR = Path(__file__).parent.parent


def test_repo_setter_none():
    """App._repo = None"""
    app = App()
    app.repo = None
    assert app._repo == "", "App._repo is set to an empty string if None"


def test_repo_getter_empty():
    """App.repo when empty with no fallbacks"""
    app = App()
    app._repo = None
    app.repo_path = Path(__file__).parent
    with pytest.raises(SystemExit) as e:
        app.repo
        assert e.type == SystemExit, "Empty App.repo with no fallbacks will abort"


def test_repo_getter_from_gitcfg():
    """App.repo from .git/config fallback"""
    app = App()
    app._repo = None
    app.repo_path = ROOTDIR
    assert app.repo == "alissa-huskey/gh-pages-cli", \
        "App.repo fallsback to remote origin url from .git/config"


def test_repo_getter_from_envvar():
    """App.repo from GITHUB_REPOSITORY env var fallback"""
    app = App()
    app._repo = None
    app.repo_path = Path(__file__).parent
    environ['GITHUB_REPOSITORY'] = "envvar-repo/envvar-username"
    assert app.repo == "envvar-repo/envvar-username", \
        "App.repo fallsback to the value of GITHUB_REPOSITORY env var"


def test_repo_getter_gitcfg_precedence():
    """App.repo getter: gitcfg takes precedence over GITHUB_REPOSITORY"""
    app = App()
    app._repo = None
    app.repo_path = ROOTDIR
    environ['GITHUB_REPOSITORY'] = "envvar-repo/envvar-username"
    assert app.repo == "alissa-huskey/gh-pages-cli", \
        "App.repo fallsback to remote origin url from .git/config"


def test_repo_getter_short():
    """App._repo setter sets short github repo format"""
    app = App()
    app.repo = "repo/username"
    assert app.repo == "repo/username", \
        "App.repo accepts repo/user format"


def test_repo_getter_long():
    """App._repo setter full github URI and returns repo/user format"""
    app = App()

    app.repo = "git@github.com:alissa-huskey/gh-pages-cli.git"
    assert app.repo == "alissa-huskey/gh-pages-cli", \
        "App.repo accepts full github URI and returns repo/user format"


def test_repo_getter_path():
    """repo_path attr and setter"""
    app = App(path=str(ROOTDIR))
    assert app.repo_path == ROOTDIR, "App.repo_path is set to a Path object"

    app = App()
    assert app.repo_path == Path.cwd(), "App.repo_path defaults to pwd"


def test_gitcfg_file():
    """gitcfg_file is a Path object to .git/config under repo_path"""
    app = App()
    assert isinstance(app.gitcfg_file, Path), "App.gitcfg_file is a Path object"
    assert app.gitcfg_file.name == "config",  "App.gitcfg_file name is config"
    assert app.gitcfg_file.parent.name == ".git", \
        "App.gitcfg_file dir name is .git"


def test_gitcfg():
    """gitcfg is a ConfigParser object of gitcfg_file contents if it exists"""
    app = App()
    app.repo_path = ROOTDIR
    assert isinstance(app.gitcfg, ConfigParser), \
        "App.gitcfg is a ConfigParser object"

    assert len(app.gitcfg.sections()), \
        "App.gitcfg is not empty if gitcfg_file exists"

    app.repo_path = path=str(Path(__file__).parent)
    assert not len(app.gitcfg.sections()), \
        "App.gitcfg is empty if gitcfg_file does not exist"


def test_data_root_setter():
    """App.data_root setter when valid path string"""
    app = App()
    app.data_root = "."
    assert isinstance(app._data_root, Path), "App._data_root is set to a Path object"
    assert app._data_root.is_absolute(), \
        "App._data_root is resolved to absolute path"


def test_data_root_setter_default():
    """App.data_root setter when None"""
    app = App()
    app.data_root = None
    assert str(app._data_root.relative_to(Path.home())) == ".ghp"


@pytest.mark.skip(reason="todo")
def test_data_root_setter_invalid():
    ...


@pytest.mark.skip(reason="todo")
def test_token_getter():
    ...


@pytest.mark.skip(reason="todo")
def test_msg():
    ...


@pytest.mark.skip(reason="todo")
def test_info():
    ...


@pytest.mark.skip(reason="todo")
def test_abort():
    ...


@pytest.mark.skip(reason="todo")
def test_style():
    ...
