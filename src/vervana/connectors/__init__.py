"""Source connectors. Each is independent and disableable via config (Part 4)."""

from vervana.connectors.agmarknet import AgmarknetConnector
from vervana.connectors.base import Connector, IngestResult

__all__ = ["AgmarknetConnector", "Connector", "IngestResult"]
