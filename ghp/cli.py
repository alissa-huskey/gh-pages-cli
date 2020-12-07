#!/usr/bin/env python3
"""Github Pages CLI
"""

from pathlib import Path
from pprint import pprint

import click
from click import style
import tabulate as tabulate_module
from tabulate import tabulate

from .app import App
from .requests import (CommitRequest, DeploysRequest, JobsRequest,
                       JobLogRequest, PagesRequest, PagesBuildsRequest,
                       RunsRequest, StatusRequest)
from .states import Ok


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
        ("URL", app.term.link(job.url, f"{App.APP.repo} > actions")),
    ]

    app.writer.indent()
    app.writer.add_block(tabulate(table, tablefmt="rst"))
    app.writer.dedent(reset=True)


@click.command()
@click.option("--repo", "-r",
              help="Github repo connected to Github Pages. (ie 'executablebooks/jupyter-book')")
@click.option("--data-root", "-d",
              help="Where to save downloaded data files.")
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


def run():
    """Run the click command"""
    main(auto_envvar_prefix="GHP")


if __name__ == "__main__":
    run()
