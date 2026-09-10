"""Source connectors. Each is independent and disableable via config (Part 4)."""

from vervana.connectors.agmarknet import AgmarknetConnector
from vervana.connectors.base import Connector, IngestResult
from vervana.connectors.context import ContextConnector
from vervana.connectors.enam import EnamConnector
from vervana.connectors.observer import ObserverConnector
from vervana.connectors.quickcommerce import QuickCommerceConnector

__all__ = [
    "AgmarknetConnector",
    "Connector",
    "ContextConnector",
    "EnamConnector",
    "IngestResult",
    "ObserverConnector",
    "QuickCommerceConnector",
]
