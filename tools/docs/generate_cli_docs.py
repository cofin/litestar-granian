"""Generate pure-Markdown CLI reference documentation from litestar_granian.cli."""

import argparse
import importlib
import re
import sys
from enum import Enum
from pathlib import Path
from typing import cast

import click

__all__ = ("DEFAULT_OUTPUT_PATH", "main", "render_cli_reference")

DEFAULT_OUTPUT_PATH = Path("docs/reference/cli.md")

_RICH_TAG_PATTERN = re.compile(
    r"\[/?(?:dim|bold|italic|underline|cyan|green|yellow|red|blue|magenta|white)(?:\s+[a-z]+)?\]"
)

_OPTION_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Server & Binding",
        "Network binding, socket handoff, HTTP/WebSocket protocol toggles, and process metadata.",
        (
            "host",
            "port",
            "fd",
            "uds",
            "uds_permissions",
            "http",
            "ws_enabled",
            "url_path_prefix",
            "backlog",
            "backpressure",
            "working_dir",
            "env_files",
            "process_name",
            "pid_file",
        ),
    ),
    (
        "Workers & Runtime",
        "Granian worker concurrency, Rust tokio runtime threads, blocking thread pools, event loops, and worker respawn policies.",
        (
            "wc",
            "runtime_mode",
            "runtime_threads",
            "runtime_blocking_threads",
            "blocking_threads",
            "blocking_threads_idle_timeout",
            "loop",
            "task_impl",
            "respawn_failed_workers",
            "respawn_interval",
            "workers_lifetime",
            "workers_kill_timeout",
            "workers_max_rss",
            "rss_sample_interval",
            "rss_samples",
        ),
    ),
    (
        "HTTP/1, HTTP/2 & TLS",
        "Protocol-specific buffer and window tuning plus TLS certificate, key, and mTLS client verification options.",
        (
            "http1_buffer_size",
            "http1_header_read_timeout",
            "http1_keep_alive",
            "http1_pipeline_flush",
            "http2_adaptive_window",
            "http2_initial_connection_window_size",
            "http2_initial_stream_window_size",
            "http2_keep_alive_interval",
            "http2_keep_alive_timeout",
            "http2_max_concurrent_streams",
            "http2_max_frame_size",
            "http2_max_headers_size",
            "http2_max_send_buffer_size",
            "ssl_certificate",
            "ssl_keyfile",
            "ssl_keyfile_password",
            "ssl_protocol_min",
            "ssl_ca",
            "ssl_crl",
            "ssl_client_verify",
            "create_self_signed_cert",
        ),
    ),
    (
        "Logging, Metrics & Static Files",
        "Granian logging and access logs, built-in Prometheus metrics exporter, and Rust-served static file mounts.",
        (
            "log_enabled",
            "log_level",
            "log_access_enabled",
            "log_access_fmt",
            "log_config",
            "metrics_enabled",
            "metrics_scrape_interval",
            "metrics_address",
            "metrics_port",
            "static_path_route",
            "static_path_mount",
            "static_path_dir_to_file",
            "static_path_expires",
        ),
    ),
    (
        "Development, Reload & Compatibility",
        "Watchfiles auto-reload filters, Litestar debug/PDB toggles, and deprecated compatibility flags.",
        (
            "reload",
            "reload_paths",
            "reload_include",
            "reload_exclude",
            "reload_ignore_dirs",
            "reload_ignore_patterns",
            "reload_ignore_paths",
            "reload_tick",
            "reload_ignore_worker_failure",
            "debug",
            "pdb",
            "in_subprocess",
            "use_litestar_logger",
        ),
    ),
)


def render_cli_reference(command: click.Command | None = None) -> str:
    """Render the complete docs/reference/cli.md Markdown document from the Click command.

    Args:
        command: Optional Click command to introspect. Defaults to ``litestar_granian.cli.run_command``.

    Returns:
        Complete Markdown string for ``docs/reference/cli.md``.
    """
    target_cmd = command if command is not None else _load_default_run_command()
    lines: list[str] = [
        "# CLI Reference",
        "",
        "```python",
        "from litestar_granian.cli import run_command",
        "```",
        "",
        "When [`GranianPlugin`](plugin.md) is registered on a Litestar application, it replaces the standard `litestar run` command with the Granian-backed implementation below. See the [Configuration & Runtime Guide](../guides/configuration.md) for usage examples.",
        "",
        "## Synopsis",
        "",
        "```bash",
        "litestar [--app MODULE:APP] run [OPTIONS]",
        "```",
        "",
    ]

    summary = _clean_text(target_cmd.help or "")
    if summary:
        lines.extend([summary, ""])

    options = [p for p in target_cmd.params if isinstance(p, click.Option) and p.name != "help"]
    option_map = {opt.name: opt for opt in options if opt.name is not None}
    rendered: set[str] = set()

    for group_title, group_desc, group_names in _OPTION_GROUPS:
        group_opts: list[click.Option] = []
        for name in group_names:
            if name in option_map:
                group_opts.append(option_map[name])
                rendered.add(name)
        if not group_opts:
            continue
        lines.extend([f"## {group_title}", "", group_desc, ""])
        lines.extend(_render_options_table(group_opts))
        lines.append("")

    remaining = [opt for opt in options if opt.name not in rendered]
    if remaining:
        lines.extend(["## Additional Options", ""])
        lines.extend(_render_options_table(remaining))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for generating or verifying docs/reference/cli.md.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit code (0 on success, 1 when stale or missing under ``--check``).
    """
    parser = argparse.ArgumentParser(description="Generate or check docs/reference/cli.md.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Target Markdown path (default: docs/reference/cli.md).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the target file matches the generated CLI reference without writing.",
    )
    args = parser.parse_args(argv)
    output_path: Path = args.output
    expected = render_cli_reference()

    if args.check:
        if not output_path.is_file():
            sys.stderr.write(f"CLI reference file is missing: {output_path}\n")
            return 1
        actual = output_path.read_text(encoding="utf-8")
        if actual != expected:
            sys.stderr.write(
                f"CLI reference file is out of date: {output_path}. "
                "Run 'uv run python -m tools.docs.generate_cli_docs' to update.\n"
            )
            return 1
        sys.stdout.write(f"CLI reference is up to date: {output_path}\n")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(expected, encoding="utf-8")
    sys.stdout.write(f"Wrote CLI reference: {output_path}\n")
    return 0


def _load_default_run_command() -> click.Command:
    """Import litestar_granian.cli.run_command.

    Returns:
        The Click command object for ``litestar run``.
    """
    cli_mod = importlib.import_module("litestar_granian.cli")
    return cast("click.Command", cli_mod.run_command)


def _render_options_table(options: list[click.Option]) -> list[str]:
    """Render a Markdown table for Click options.

    Args:
        options: Click options to format.

    Returns:
        Markdown table lines.
    """
    rows: list[str] = ["| Option | Type | Default | Description |", "| --- | --- | --- | --- |"]
    for opt in options:
        flags = _format_option_flags(opt)
        type_name = "`flag`" if opt.is_flag else f"`{_format_param_type(opt)}`"
        default = _format_default(opt)
        description = _clean_single_line(opt.help or "")
        if opt.required:
            description = f"**Required.** {description}".strip()
        env_text = _format_envvars(opt.envvar)
        if env_text:
            if description and not description.endswith("."):
                description = f"{description}."
            description = f"{description} {env_text}".strip()
        rows.append(f"| {flags} | {type_name} | {default} | {description} |")
    return rows


def _format_option_flags(opt: click.Option) -> str:
    """Format primary and secondary option flags without adjacent trailing punctuation.

    Args:
        opt: Click option instance.

    Returns:
        Formatted Markdown code spans for the option flags.
    """
    if opt.secondary_opts and len(opt.opts) == 1 and len(opt.secondary_opts) == 1:
        primary = opt.opts[0]
        secondary = opt.secondary_opts[0]
        if primary.startswith("--") and secondary.startswith("--"):
            return f"`{primary}/{secondary}`"
    all_flags = [*opt.opts, *opt.secondary_opts]
    return " ".join(f"`{flag}`" for flag in all_flags)


def _format_envvars(envvar: str | list[str] | tuple[str, ...] | None) -> str:
    """Format environment variable names without placing punctuation adjacent to code spans.

    Args:
        envvar: Configured Click envvar string or sequence.

    Returns:
        Formatted environment variable hint or empty string.
    """
    if not envvar:
        return ""
    names = [envvar] if isinstance(envvar, str) else [str(item) for item in envvar if item]
    if not names:
        return ""
    formatted = " or ".join(f"`{name}`" for name in names)
    return f"Env: {formatted}"


def _format_param_type(param: click.Parameter) -> str:
    """Return a clean human-readable type name for a Click parameter.

    Args:
        param: Click parameter instance.

    Returns:
        Normalized parameter type label.
    """
    if isinstance(param.type, click.Choice):
        choices = " | ".join(str(c) for c in param.type.choices)
        return f"choice({choices})"
    type_name = getattr(param.type, "name", None) or type(param.type).__name__
    return str(type_name).lower()


def _format_default(opt: click.Option) -> str:
    """Format a Click option default while filtering Click 8.3+ Sentinel.UNSET objects.

    Args:
        opt: Click option instance.

    Returns:
        Markdown cell string for the option default.
    """
    show_default: object = opt.show_default
    if isinstance(show_default, str) and show_default:
        return f"`{show_default}`"
    default: object = opt.default
    if isinstance(default, Enum):
        default = default.value
    if default is None or default == ():
        return "`False`" if opt.is_flag else "-"
    type_name = type(default).__name__
    repr_text = repr(default)
    if "Sentinel" in type_name or "UNSET" in repr_text:
        return "`False`" if opt.is_flag else "-"
    if isinstance(default, bool):
        return f"`{default}`"
    if isinstance(default, (int, float)):
        return f"`{default}`"
    if isinstance(default, str):
        return f'`"{default}"`' if default else '`""`'
    return "-"


def _clean_text(text: str) -> str:
    """Strip Rich console tags and normalize whitespace while preserving paragraphs.

    Args:
        text: Raw help text.

    Returns:
        Normalized multi-paragraph text.
    """
    stripped = _RICH_TAG_PATTERN.sub("", text).strip()
    paragraphs = [
        " ".join(line.strip() for line in block.splitlines() if line.strip()) for block in stripped.split("\n\n")
    ]
    return "\n\n".join(p for p in paragraphs if p)


def _clean_single_line(text: str) -> str:
    """Strip Rich console tags and collapse newlines/pipes for Markdown table cells.

    Args:
        text: Raw help text.

    Returns:
        Escaped single-line Markdown table cell content.
    """
    cleaned = _clean_text(text)
    single_line = " ".join(cleaned.split())
    return single_line.replace("|", "\\|")


if __name__ == "__main__":
    raise SystemExit(main())
