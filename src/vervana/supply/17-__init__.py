"""Supply-side layer (M11): satellite + agromet feeds, and the Google ALU/AMED seam.

ALU (crop map: what crop, how much area, which season) and AMED (sowing/harvest
event timing) are partner-gated Google APIs - access requested, not granted - so
their connectors are honest scaffolds. The layer works today on the fallback
path: Sentinel-2 NDVI (Copernicus Data Space) and IMD district rainfall feed the
same signal kinds, and the Google connector drops in when approval lands.
"""

from vervana.supply.scaffold import FeedStatus, PartnerAccessPending, PartnerFeed
from vervana.supply.zones import SupplyZone, get_zone, load_zones

__all__ = [
    "FeedStatus",
    "PartnerAccessPending",
    "PartnerFeed",
    "SupplyZone",
    "get_zone",
    "load_zones",
]
