"""Source connectors. Each is independent and disableable via config (Part 4)."""

from vervana.connectors.agmarknet import AgmarknetConnector
from vervana.connectors.base import Connector, IngestResult
from vervana.connectors.quickcommerce import QuickCommerceConnector

__all__ = ["AgmarknetConnector", "Connector", "IngestResult", "QuickCommerceConnector"]
