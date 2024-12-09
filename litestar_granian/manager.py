from __future__ import annotations

import signal
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from litestar.cli._utils import (  # pyright: ignore[reportPrivateUsage]
    console,  # noqa: PLC2701
)

if TYPE_CHECKING:
    from granian import Granian


@dataclass
class ProcessManager:
    """Manages the lifecycle of the Granian server process."""

    server: Granian
    shutdown_callback: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        """Set up signal handlers after initialization."""
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

    def handle_signal(self, signum: int, frame: Any) -> None:
        """Handle process signals gracefully."""
        try:
            self.server.shutdown()  # type: ignore[no-untyped-call]
            if self.shutdown_callback:
                self.shutdown_callback()
        finally:
            console.print("[yellow]Granian process stopped.[/]")
            sys.exit(0)

    def run(self) -> None:
        """Run the server with proper signal handling."""
        try:
            self.server.serve()
        except KeyboardInterrupt:
            self.server.shutdown()  # type: ignore[no-untyped-call]
            if self.shutdown_callback:
                self.shutdown_callback()
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Error running server: {e}[/]")
            sys.exit(1)
        finally:
            console.print("[yellow]Granian process stopped.[/]")
