"""ERA5 taken directly from ECMWF (MARS, or the Copernicus Climate Data Store).

This is the **ECMWF-direct workstream**, kept separate from the ARCO copy on
Google Cloud (:mod:`metbazarr.sources.era5_arco`) so the two are never mixed:
stores from here will say so in ``source_dataset`` and be named
``<DOMAIN>_<start>-<end>_ERA5-ECMWF.zarr``. It is the route FLEXPART's
preparation tool, flex_extract, takes, and is needed to compare GLIDE and
FLEXPART on identical input (GLIDE task B13).

Not implemented yet: it waits for MARS access (roadmap task M2b).
"""

from __future__ import annotations


class Era5EcmwfNotImplemented(NotImplementedError):
    """ECMWF-direct ERA5 is not available yet."""


def not_implemented() -> None:
    raise Era5EcmwfNotImplemented(
        "source type 'era5_ecmwf' (ERA5 directly from ECMWF MARS or the CDS) is not "
        "implemented yet: it waits for MARS access (roadmap task M2b). Use "
        "'era5_arco' for the ARCO copy on Google Cloud."
    )
