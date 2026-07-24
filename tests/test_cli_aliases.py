from __future__ import annotations

from click import Option
from click.testing import CliRunner
from litestar.cli.commands.core import run_command as litestar_run_command

from litestar_granian.cli import run_command


def test_litestar_run_surface_comes_before_granian_extensions() -> None:
    expected_litestar_parameters = [
        "reload",
        "reload_paths",
        "reload_include",
        "reload_exclude",
        "port",
        "wc",
        "host",
        "fd",
        "uds",
        "debug",
        "pdb",
        "ssl_certificate",
        "ssl_keyfile",
        "create_self_signed_cert",
    ]

    assert [parameter.name for parameter in run_command.params[:14]] == expected_litestar_parameters
    assert run_command.params[14].name == "uds_permissions"
    assert [parameter.name for parameter in run_command.params[-2:]] == [
        "in_subprocess",
        "use_litestar_logger",
    ]


def test_every_litestar_run_option_is_supported() -> None:
    litestar_options = {
        option for parameter in litestar_run_command.params for option in (*parameter.opts, *parameter.secondary_opts)
    }
    plugin_options = {
        option for parameter in run_command.params for option in (*parameter.opts, *parameter.secondary_opts)
    }

    assert litestar_options <= plugin_options


def test_help_exposes_only_truthful_compatibility_aliases() -> None:
    result = CliRunner().invoke(run_command, ["--help"], terminal_width=200)

    assert result.exit_code == 0
    assert "--ssl-certfile" in result.output
    assert "--ssl-keyfile" in result.output
    assert "--uds" in result.output
    assert "--unix-domain-socket" in result.output
    assert "-U" in result.output
    assert "--reload-dir" in result.output
    assert "--reload-paths" in result.output
    assert "-I" in result.output
    assert "--reload-include" in result.output
    assert "-E" in result.output
    assert "--reload-exclude" in result.output
    assert "-F" in result.output
    assert "--fd" in result.output
    assert "--file-descriptor" in result.output
    assert "--in-subprocess" in result.output
    assert "--no-subprocess" in result.output
    assert "--use-litestar-logger" in result.output
    logger_option = next(parameter for parameter in run_command.params if parameter.name == "use_litestar_logger")
    assert "--no-litestar-logger" in logger_option.secondary_opts


def test_help_descriptions_explain_the_combined_litestar_granian_contract() -> None:
    expected_help = {
        "reload": "Enable auto reload when application files change",
        "host": "Host address to bind to",
        "port": "Port to bind to",
        "uds": "Unix Domain Socket path",
        "http": "HTTP version to use: auto, HTTP/1, or HTTP/2",
        "pdb": "Drop into PDB on an exception",
        "wc": ("Number of Granian application workers (processes on GIL builds; threads on free-threaded builds)"),
        "runtime_threads": (
            "Number of Rust network I/O threads per worker; does not control Python application parallelism"
        ),
        "runtime_mode": (
            "Granian Rust runtime mode (single/multi-threaded/auto-detect); ASGI auto resolves to multi-threaded"
        ),
        "ssl_certificate": "SSL certificate file (Granian alias: --ssl-certificate)",
        "ssl_keyfile": "SSL private key file (PKCS#8 format only)",
        "reload_paths": "Paths to watch for changes; repeatable",
        "reload_include": "Glob patterns for files to include when watching for file changes",
        "reload_exclude": "Glob patterns for files to exclude when watching for file changes",
        "workers_kill_timeout": "Granian worker shutdown timeout; the parent deadline adds five seconds",
        "log_config": "Explicit Granian JSON dictConfig; overrides generated log styles",
        "process_name": "Set a custom name for Granian processes",
    }

    actual_help = {parameter.name: parameter.help for parameter in run_command.params if isinstance(parameter, Option)}

    for name, description in expected_help.items():
        assert actual_help[name] == description
