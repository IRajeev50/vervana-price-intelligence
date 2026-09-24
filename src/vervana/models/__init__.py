"""ORM models. Importing this module registers every table on Base.metadata."""

from vervana.models.aspirational import AspirationalDistrict
from vervana.models.context import ContextSignal
from vervana.models.crop_production import CropDistrictYearRollup, CropProductionRecord
from vervana.models.entities import Alias, Commodity, Grade, Market, Variety
from vervana.models.forecast_log import ProspectiveForecast
from vervana.models.ingest import IngestRun
from vervana.models.intelligence import IntelligenceReportRecord
from vervana.models.invoice import Invoice
from vervana.models.observations import PriceObservation
from vervana.models.observer import Observer
from vervana.models.retail import RetailOfferDetail
from vervana.models.review import AliasReview
from vervana.models.sourcing import Buyer, SupplierContact
from vervana.models.units import UnitConvention

__all__ = [
    "Alias",
    "AliasReview",
    "AspirationalDistrict",
    "Buyer",
    "Commodity",
    "ContextSignal",
    "CropDistrictYearRollup",
    "CropProductionRecord",
    "Grade",
    "IngestRun",
    "IntelligenceReportRecord",
    "Invoice",
    "Market",
    "Observer",
    "PriceObservation",
    "ProspectiveForecast",
    "RetailOfferDetail",
    "SupplierContact",
    "UnitConvention",
    "Variety",
]
