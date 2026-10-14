"""RepoGym command-line interface."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from typer._click.core import Context
from typer._click.exceptions import ClickException
from typer.core import TyperGroup

from repogym import __version__
from repogym.analytics.cli import analyze
from repogym.archives.cli import app as archive_app
from repogym.authoring import lint_task, scaffold_task
from repogym.batch import generate_batch_report, load_batch, run_batch
from repogym.bundles import export_task_bundle, import_task_bundle
from repogym.cache import ExecutionCache
from repogym.catalog.cli import app as catalog_app
from repogym.comparison import generate_comparison
from repogym.doctor import diagnose_task
from repogym.environment import collect_runtime_environment, render_environment_terminal
from repogym.exceptions import (
    AuthoringError,
    BatchError,
    CacheError,
    ExecutionError,
    ExecutorUnavailableError,
    RepoGymError,
)
from repogym.executors import DockerExecutor, LocalExecutor, executor_capabilities, executor_policy
from repogym.executors.base import Executor
from repogym.exit_codes import ExitCode
from repogym.grader import grade_submission
from repogym.history.cli import app as history_app
from repogym.loader import load_task
from repogym.plugins import discover_plugins
from repogym.reports import generate_report, load_run, render_terminal
from repogym.security import redact_sensitive_text
from repogym.validator import validate_task
from repogym.verifier import verify_task


class RepoGymGroup(TyperGroup):
    """Convert unexpected command failures to the stable internal-error code."""

    def invoke(self, ctx: Context) -> object:
        try:
            return super().invoke(ctx)
        except (ClickException, typer.Exit, typer.Abort):
            raise
        except OSError as exc:
            _print_error(exc)
            raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR)) from exc
        except Exception as exc:
            _print_error(exc)
            raise typer.Exit(int(ExitCode.INTERNAL_ERROR)) from exc


app = typer.Typer(
    help="Build and grade reproducible AI coding tasks.",
    no_args_is_help=True,
    cls=RepoGymGroup,
    epilog=(
        "Exit codes: 0 success, 10 invalid task/input, 20 execution failed, "
        "30 score below 100, 40 environment error, 70 internal error."
    ),
)
bundle_app = typer.Typer(help="Export and import verified portable task bundles.")
cache_app = typer.Typer(help="Inspect and maintain the incremental execution cache.")
batch_app = typer.Typer(help="Run and replay deterministic multi-task evaluations.")
app.add_typer(bundle_app, name="bundle")
app.add_typer(cache_app, name="cache")
app.add_typer(batch_app, name="batch")
app.add_typer(history_app, name="runs")
app.add_typer(archive_app, name="archive")
app.add_typer(catalog_app, name="catalog")
app.command("analyze")(analyze)
console = Console()
error_console = Console(stderr=True)
_debug = False


@app.callback()
def main(debug: Annotated[bool, typer.Option("--debug", help="Show tracebacks.")] = False) -> None:
    global _debug
    _debug = debug


def _print_error(exc: Exception) -> None:
    if _debug:
        traceback.print_exc()
    else:
        error_console.print(f"[red]Error:[/red] {escape(redact_sensitive_text(str(exc)))}")


def _fail(exc: Exception, code: ExitCode) -> None:
    _print_error(exc)
    raise typer.Exit(int(code))


def _configured_executor(
    backend: Literal["local", "docker"],
    docker_image: str | None,
    docker_allow_network: bool,
    docker_cpus: float,
    docker_memory_mb: int,
    docker_pids_limit: int,
) -> Executor:
    if backend == "local":
        return LocalExecutor()
    if docker_image is None:
        raise RepoGymError("--docker-image is required when --executor docker is selected")
    try:
        executor = DockerExecutor(
            docker_image,
            network_disabled=not docker_allow_network,
            cpu_limit=docker_cpus,
            memory_limit_bytes=docker_memory_mb * 1024 * 1024,
            process_limit=docker_pids_limit,
        )
    except ValueError as exc:
        raise RepoGymError(str(exc)) from exc
    capabilities = executor.capabilities()
    if not capabilities.available:
        raise ExecutorUnavailableError(capabilities.availability_reason)
    return executor


@app.command("list")
def list_tasks(
    tasks_dir: Annotated[Path, typer.Option(help="Directory containing tasks.")] = Path("tasks"),
) -> None:
    """List discoverable tasks."""
    if not tasks_dir.is_dir():
        _fail(RepoGymError(f"Tasks directory does not exist: {tasks_dir}"), ExitCode.TASK_INVALID)
    table = Table("ID", "Title", "Difficulty", "Language")
    found = 0
    for directory in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
        try:
            task = load_task(directory)
        except RepoGymError:
            continue
        table.add_row(task.id, task.title, task.difficulty, task.language)
        found += 1
    console.print(table)
    console.print(f"{found} task(s)")


@app.command()
def validate(task: Annotated[Path, typer.Argument(help="Task directory.")]) -> None:
    """Validate a task definition and its files."""
    report = validate_task(task)
    for check in report.checks:
        console.print(f"[green]PASS[/green] {check}")
    if report.errors:
        for error in report.errors:
            error_console.print(f"[red]FAIL[/red] {escape(redact_sensitive_text(error, [task]))}")
        raise typer.Exit(int(ExitCode.TASK_INVALID))
    console.print("\n[bold green]Validation passed.[/bold green]")


def _render_authoring_report(task: Path) -> tuple[bool, int]:
    report = lint_task(task)
    for check in report.validation.checks:
        console.print(f"[green]PASS[/green] {check}")
    for error in report.validation.errors:
        error_console.print(f"[red]FAIL[/red] {escape(redact_sensitive_text(error, [task]))}")
    for diagnostic in report.diagnostics:
        label = "FAIL" if diagnostic.status == "error" else "WARN"
        style = "red" if diagnostic.status == "error" else "yellow"
        stream = error_console if diagnostic.status == "error" else console
        stream.print(f"[{style}]{label}[/] ({diagnostic.code}) {escape(diagnostic.message)}")
    warnings = sum(item.status == "warning" for item in report.diagnostics)
    return report.valid, warnings


@app.command("init-task")
def init_task(
    task_id: Annotated[
        str | None,
        typer.Argument(help="Lowercase hyphenated task ID."),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Human-readable task title."),
    ] = None,
    tasks_dir: Annotated[
        Path,
        typer.Option("--tasks-dir", help="Parent directory for task definitions."),
    ] = Path("tasks"),
    non_interactive: Annotated[
        bool,
        typer.Option("--non-interactive", help="Reject missing values instead of prompting."),
    ] = False,
) -> None:
    """Create an atomically published, structurally valid task template."""
    if non_interactive and (task_id is None or title is None):
        _fail(
            AuthoringError("--non-interactive requires TASK_ID and --title"),
            ExitCode.TASK_INVALID,
        )
    resolved_id = task_id or typer.prompt("Task ID")
    resolved_title = title or typer.prompt("Task title")
    try:
        task = scaffold_task(tasks_dir, resolved_id, resolved_title)
    except AuthoringError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    displayed = redact_sensitive_text(str(task), [Path.cwd()])
    console.print(f"[green]Created[/green] {escape(displayed)}")
    _render_authoring_report(task)
    console.print("Replace the TODO prompt, tests, and reference patch before verification.")


@app.command("lint-task")
def lint_task_command(
    task: Annotated[Path, typer.Argument(help="Task directory.")],
) -> None:
    """Check author completeness and reproducibility risks."""
    try:
        valid, warnings = _render_authoring_report(task)
    except AuthoringError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    if not valid:
        raise typer.Exit(int(ExitCode.TASK_INVALID))
    if warnings:
        console.print(f"\n[bold yellow]Author lint completed with {warnings} warning(s).[/]")
    else:
        console.print("\n[bold green]Author lint passed.[/bold green]")


@app.command()
def doctor(task: Annotated[Path, typer.Argument(help="Task directory.")]) -> None:
    """Diagnose whether a task can run in the current environment."""
    report = diagnose_task(task)
    styles = {"pass": "green", "warning": "yellow", "fail": "red"}  # nosec B105
    labels = {"pass": "PASS", "warning": "WARN", "fail": "FAIL"}  # nosec B105
    for check in report.checks:
        message = (
            check.message
            if check.name == "test command"
            else redact_sensitive_text(check.message, [task])
        )
        console.print(
            f"[{styles[check.status]}]{labels[check.status]}[/] "
            f"{escape(check.name)}: {escape(message)}"
        )
    if not report.healthy:
        raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR))


@app.command()
def verify(
    task: Annotated[Path, typer.Argument(help="Task directory.")],
    executor_backend: Annotated[
        Literal["local", "docker"], typer.Option("--executor", help="Execution backend.")
    ] = "local",
    docker_image: Annotated[
        str | None, typer.Option("--docker-image", help="Explicit Docker/OCI image reference.")
    ] = None,
    docker_allow_network: Annotated[
        bool, typer.Option("--docker-allow-network", help="Allow container network access.")
    ] = False,
    docker_cpus: Annotated[float, typer.Option("--docker-cpus", min=0.01)] = 1.0,
    docker_memory_mb: Annotated[int, typer.Option("--docker-memory-mb", min=1)] = 512,
    docker_pids_limit: Annotated[int, typer.Option("--docker-pids-limit", min=1)] = 128,
) -> None:
    """Prove that the starter fails and the reference patch passes."""
    try:
        runner = _configured_executor(
            executor_backend,
            docker_image,
            docker_allow_network,
            docker_cpus,
            docker_memory_mb,
            docker_pids_limit,
        )
        report = (
            verify_task(task) if executor_backend == "local" else verify_task(task, executor=runner)
        )
    except ExecutorUnavailableError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    except ExecutionError as exc:
        _fail(exc, ExitCode.EXECUTION_FAILED)
    except RepoGymError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    initial_failed = report.initial.stdout + report.initial.stderr
    console.print("[green]PASS[/green] Starter produced the expected failures")
    console.print(f"[green]PASS[/green] Reference patch changed: {', '.join(report.patch_files)}")
    console.print("[green]PASS[/green] Reference solution passed all tests")
    console.print(f"[green]PASS[/green] Task fingerprint: {report.task_fingerprint}")
    console.print(f"\n[bold green]Verification passed for {report.task_id}.[/bold green]")
    if _debug:
        console.print(initial_failed)


@app.command()
def grade(
    task: Annotated[Path, typer.Argument(help="Task directory.")],
    submission: Annotated[Path, typer.Option("--submission", help="Candidate code directory.")],
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Disable cache reuse.")] = False,
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Execution cache directory.")
    ] = Path(".repogym/cache"),
    executor_backend: Annotated[
        Literal["local", "docker"], typer.Option("--executor", help="Execution backend.")
    ] = "local",
    docker_image: Annotated[
        str | None, typer.Option("--docker-image", help="Explicit Docker/OCI image reference.")
    ] = None,
    docker_allow_network: Annotated[
        bool, typer.Option("--docker-allow-network", help="Allow container network access.")
    ] = False,
    docker_cpus: Annotated[float, typer.Option("--docker-cpus", min=0.01)] = 1.0,
    docker_memory_mb: Annotated[int, typer.Option("--docker-memory-mb", min=1)] = 512,
    docker_pids_limit: Annotated[int, typer.Option("--docker-pids-limit", min=1)] = 128,
) -> None:
    """Grade a candidate submission."""
    try:
        runner = _configured_executor(
            executor_backend,
            docker_image,
            docker_allow_network,
            docker_cpus,
            docker_memory_mb,
            docker_pids_limit,
        )
        run_dir = grade_submission(
            task,
            submission,
            executor=runner,
            cache_root=None if no_cache else cache_dir,
        )
        result, _, _ = load_run(run_dir)
    except ExecutorUnavailableError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    except CacheError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    except RepoGymError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    render_terminal(result, console)
    console.print(
        f"Run artifacts: [bold]{escape(redact_sensitive_text(str(run_dir), [Path.cwd()]))}[/bold]"
    )
    if result.status != "completed":
        raise typer.Exit(int(ExitCode.EXECUTION_FAILED))
    if result.score < 100:
        raise typer.Exit(int(ExitCode.SCORE_NOT_PASSED))


@app.command()
def report(
    run: Annotated[Path, typer.Argument(help="Run directory.")],
    format_name: Annotated[
        Literal["terminal", "json", "html", "junit", "sarif"],
        typer.Option("--format", help="Report format."),
    ] = "terminal",
    output: Annotated[Path | None, typer.Option("--output", help="Output file.")] = None,
) -> None:
    """Render an existing grade result."""
    if format_name == "html" and output is None:
        _fail(RepoGymError("--output is required for HTML reports"), ExitCode.TASK_INVALID)
    try:
        rendered = generate_report(run, format_name, output, console)
    except RepoGymError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    if rendered is not None and output is None:
        console.print(rendered, markup=False, soft_wrap=True)
    elif output is not None:
        console.print(f"Report written to {escape(redact_sensitive_text(str(output)))}")


@app.command()
def compare(
    run_a: Annotated[Path, typer.Argument(help="Baseline run directory.")],
    run_b: Annotated[Path, typer.Argument(help="Comparison run directory.")],
    format_name: Annotated[
        Literal["terminal", "json"], typer.Option("--format", help="Comparison format.")
    ] = "terminal",
    output: Annotated[Path | None, typer.Option("--output", help="Output file.")] = None,
) -> None:
    """Compare two persisted grading runs."""
    try:
        rendered = generate_comparison(run_a, run_b, format_name, console, output)
    except RepoGymError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    if rendered is not None and output is None:
        console.print(rendered, markup=False, soft_wrap=True)
    elif output is not None:
        console.print(f"Comparison written to {escape(redact_sensitive_text(str(output)))}")


@bundle_app.command("export")
def export_bundle(
    task: Annotated[Path, typer.Argument(help="Task directory.")],
    output: Annotated[Path, typer.Argument(help="New .zip bundle path.")],
) -> None:
    """Export a validated task as an integrity-checked ZIP package."""
    try:
        manifest = export_task_bundle(task, output)
    except RepoGymError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    output_text = redact_sensitive_text(str(output), [Path.cwd()])
    console.print(f"Exported {manifest.task_id} ({len(manifest.files)} files) to {output_text}")


@bundle_app.command("import")
def import_bundle(
    bundle: Annotated[Path, typer.Argument(help="Verified .zip task bundle.")],
    destination: Annotated[
        Path, typer.Option("--destination", help="Existing parent directory for the task.")
    ],
) -> None:
    """Verify and atomically import a task bundle."""
    try:
        task_directory = import_task_bundle(bundle, destination)
    except RepoGymError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    task_text = redact_sensitive_text(str(task_directory), [Path.cwd()])
    console.print(f"Imported task to {task_text}")


@cache_app.command("list")
def list_cache(
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Execution cache directory.")
    ] = Path(".repogym/cache"),
) -> None:
    """List cache entries and integrity state."""
    try:
        entries = ExecutionCache(cache_dir).inspect()
    except (CacheError, OSError) as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    table = Table("Key", "Status", "Bytes")
    for entry in entries:
        table.add_row(entry.key, "valid" if entry.valid else "corrupt", str(entry.size_bytes))
    console.print(table)
    console.print(f"{len(entries)} cache entr{'y' if len(entries) == 1 else 'ies'}")


@cache_app.command("verify")
def verify_cache(
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Execution cache directory.")
    ] = Path(".repogym/cache"),
) -> None:
    """Verify every published cache entry without changing it."""
    try:
        entries = ExecutionCache(cache_dir).inspect()
    except (CacheError, OSError) as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    corrupt = [entry for entry in entries if not entry.valid]
    for entry in corrupt:
        error_console.print(f"[red]FAIL[/red] {entry.key}: {escape(entry.error or 'invalid')}")
    if corrupt:
        raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR))
    console.print(f"[green]PASS[/green] {len(entries)} cache entries verified")


@cache_app.command("clear")
def clear_cache(
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Execution cache directory.")
    ] = Path(".repogym/cache"),
) -> None:
    """Remove entries present when cache clearing begins."""
    try:
        removed = ExecutionCache(cache_dir).clear()
    except (CacheError, OSError) as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    console.print(f"Removed {removed} cache entr{'y' if removed == 1 else 'ies'}")


def _emit_batch_report(
    batch_directory: Path,
    format_name: Literal["terminal", "json", "junit", "sarif"],
    output: Path | None,
) -> None:
    rendered = generate_batch_report(batch_directory, format_name, output, console)
    if rendered is not None and output is None:
        console.print(rendered, markup=False)
    elif output is not None:
        console.print(f"Batch report written to {escape(redact_sensitive_text(str(output)))}")


@batch_app.command("run")
def run_batch_command(
    manifest: Annotated[Path, typer.Argument(help="Versioned YAML batch manifest.")],
    workers: Annotated[
        int, typer.Option("--workers", min=1, max=32, help="Maximum independent grading groups.")
    ] = 1,
    format_name: Annotated[
        Literal["terminal", "json", "junit", "sarif"],
        typer.Option("--format", help="Summary format."),
    ] = "terminal",
    output: Annotated[Path | None, typer.Option("--output", help="Output report file.")] = None,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Disable cache reuse.")] = False,
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Execution cache directory.")
    ] = Path(".repogym/cache"),
    runs_dir: Annotated[
        Path, typer.Option("--runs-dir", help="Individual run artifact directory.")
    ] = Path(".repogym/runs"),
    batches_dir: Annotated[
        Path, typer.Option("--batches-dir", help="Batch artifact directory.")
    ] = Path(".repogym/batches"),
) -> None:
    """Grade every manifest job, continuing after individual failures."""
    try:
        batch_directory = run_batch(
            manifest,
            output_root=batches_dir,
            runs_root=runs_dir,
            cache_root=None if no_cache else cache_dir,
            max_workers=workers,
        )
        batch = load_batch(batch_directory)
        _emit_batch_report(batch_directory, format_name, output)
    except KeyboardInterrupt:
        _fail(
            ExecutionError("Batch cancelled; active processes were asked to stop"),
            ExitCode.EXECUTION_FAILED,
        )
    except BatchError as exc:
        _fail(exc, ExitCode.TASK_INVALID)
    except RepoGymError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    if format_name == "terminal" or output is not None:
        artifact = redact_sensitive_text(str(batch_directory), [Path.cwd()])
        console.print(f"Batch artifacts: [bold]{escape(artifact)}[/bold]")
    if batch.exit_code != ExitCode.SUCCESS:
        raise typer.Exit(int(batch.exit_code))


@batch_app.command("report")
def report_batch_command(
    batch_run: Annotated[Path, typer.Argument(help="Batch directory or batch.json path.")],
    format_name: Annotated[
        Literal["terminal", "json", "junit", "sarif"],
        typer.Option("--format", help="Summary format."),
    ] = "terminal",
    output: Annotated[Path | None, typer.Option("--output", help="Output report file.")] = None,
) -> None:
    """Replay a persisted batch result without executing task code."""
    try:
        batch = load_batch(batch_run)
        _emit_batch_report(batch_run, format_name, output)
    except RepoGymError as exc:
        _fail(exc, ExitCode.ENVIRONMENT_ERROR)
    if batch.exit_code != ExitCode.SUCCESS:
        raise typer.Exit(int(batch.exit_code))


@app.command()
def version() -> None:
    """Show the installed RepoGym version."""
    console.print(__version__)


@app.command("environment")
def environment_command(
    format_name: Annotated[
        Literal["terminal", "json"],
        typer.Option("--format", help="Environment output format."),
    ] = "terminal",
) -> None:
    """Show the non-sensitive runtime snapshot used by new grading runs."""
    environment = collect_runtime_environment()
    if format_name == "json":
        console.print(
            json.dumps(
                environment.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            markup=False,
            soft_wrap=True,
        )
    else:
        render_environment_terminal(environment, console)


@app.command("executor-info")
def executor_info(
    backend: Annotated[
        Literal["local", "docker"], typer.Option("--backend", help="Backend to inspect.")
    ] = "local",
    docker_image: Annotated[
        str, typer.Option("--docker-image", help="Docker/OCI image policy to inspect.")
    ] = "python:3.12-slim",
    format_name: Annotated[
        Literal["terminal", "json"], typer.Option("--format", help="Diagnostic format.")
    ] = "terminal",
) -> None:
    """Show backend availability, isolation capabilities, and effective policy."""
    try:
        executor: Executor = LocalExecutor() if backend == "local" else DockerExecutor(docker_image)
    except ValueError as exc:
        _fail(RepoGymError(str(exc)), ExitCode.TASK_INVALID)
    capabilities = executor_capabilities(executor)
    policy = executor_policy(executor)
    if format_name == "json":
        console.print(
            json.dumps(
                {
                    "capabilities": capabilities.model_dump(mode="json"),
                    "policy": policy.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            markup=False,
            soft_wrap=True,
        )
    else:
        table = Table("Property", "Value")
        for name, value in capabilities.model_dump(mode="json").items():
            table.add_row(f"capability.{name}", str(value))
        for name, value in policy.model_dump(mode="json").items():
            table.add_row(f"policy.{name}", str(value))
        console.print(table)
    if not capabilities.available:
        error_console.print(
            "[red]FAIL[/red] Backend unavailable; RepoGym will not fall back to local execution."
        )
        raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR))


@app.command()
def plugins() -> None:
    """List compatible extensions and isolated discovery failures."""
    registry = discover_plugins()
    table = Table("Entry point", "Status", "Details")
    styles = {
        "loaded": "green",
        "failed": "red",
        "incompatible": "yellow",
        "conflict": "yellow",
    }
    for diagnostic in registry.diagnostics:
        table.add_row(
            escape(diagnostic.entry_point),
            f"[{styles[diagnostic.status]}]{diagnostic.status}[/]",
            escape(diagnostic.message),
        )
    console.print(table)
    rejected = sum(item.status != "loaded" for item in registry.diagnostics)
    console.print(f"{len(registry.plugins)} plugin(s) loaded; {rejected} issue(s) isolated")


if __name__ == "__main__":
    app()
