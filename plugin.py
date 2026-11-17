"""Milo bot Runner entry point loaded as a synthetic Python package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from milo_core.sdk_plugin import MiloBotPlugin
else:
    from .milo_core.sdk_plugin import MiloBotPlugin


def create_plugin() -> MiloBotPlugin:
    """Return an uninitialized instance for Milo bot to configure and load."""
    return MiloBotPlugin()
