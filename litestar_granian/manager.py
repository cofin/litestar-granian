import sys
from typing import TYPE_CHECKING, Union

from granian.errors import FatalError

if TYPE_CHECKING:
    from granian.server.mp import MPServer as MPGranian
    from granian.server.mt import MTServer as MTGranian
    from rich.console import Console


class ProcessManager:
    """Manages the lifecycle of the Granian server process."""

    def __init__(self, server: Union["MPGranian", "MTGranian"], console: "Console") -> None:
        self.server = server
        self.console = console

    def run(self) -> None:
        """Run the server with proper signal handling."""
        try:
            self.server.serve()
        except FatalError:
            import click

            click.exceptions.Exit(1)
        finally:
            self.console.print("[yellow]Granian workers stopped.[/]")
            sys.exit(0)
