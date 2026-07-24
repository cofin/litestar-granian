"""Expose the public plugin that installs the supervised Granian command."""

from typing import TYPE_CHECKING, Literal

from litestar.plugins import CLIPluginProtocol, InitPlugin

if TYPE_CHECKING:
    try:
        from rich_click import Group
    except ImportError:
        from click import Group

    from litestar.config.app import AppConfig

StaticMode = Literal["off", "auto"]


class GranianPlugin(InitPlugin, CLIPluginProtocol):
    """Register the supervised Granian runtime with Litestar's CLI.

    Args:
        static: Native static-file discovery mode. ``"off"`` keeps Litestar's
            static routing. ``"auto"`` consumes exactly one compatible static
            provider when its configuration is safe, otherwise it falls back
            to Litestar. Explicit CLI mounts always take precedence.

    Raises:
        ValueError: If ``static`` is not one of the documented literal values.
    """

    __slots__ = ("static",)

    static: StaticMode

    def __init__(
        self,
        *,
        static: StaticMode = "off",
    ) -> None:
        if static not in {"off", "auto"}:
            message = "static must be 'off' or 'auto'"
            raise ValueError(message)
        self.static = static

    def on_cli_init(self, cli: "Group") -> None:  # ruff: ignore[no-self-use]
        from litestar_granian.cli import run_command

        cli.add_command(run_command)

    def on_app_init(self, app_config: "AppConfig") -> "AppConfig":
        return super().on_app_init(app_config)
