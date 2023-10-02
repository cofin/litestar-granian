from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from litestar_granian.cli import run_command

if TYPE_CHECKING:
    from click import Group

 


class GranianPlugin(InitPluginProtocol, CLIPluginProtocol ):
    """Granian server plugin."""
    __slots__ = ()

    def on_cli_init(self, cli: Group) -> None:
        from litestar.cli.main import litestar_group as cli

        cli.add_command(run_command)
        return super().on_cli_init(cli)
