from __future__ import annotations

from types import SimpleNamespace


class OfflineSDOHNetworkError(RuntimeError):
    pass


def install_offline_sdoh() -> None:
    """Force the current worker process into a no-network SDOH mode.

    Disco Inferno workers are isolated processes, so it is safe to replace the
    SDOH module's lookup entry points process-locally. This is stronger than
    trying to pass flags through individual message builders: any accidental
    SDOH lookup in the worker returns a neutral local value, and any direct HTTP
    access from hl7_demo.sdoh is blocked.
    """

    from hl7_demo import messages as hl7_messages
    from hl7_demo import sdoh as sdoh_module

    def no_air_quality(*_args, **_kwargs):
        return {}

    def no_poverty(*_args, **_kwargs):
        return None

    def no_places(*_args, **_kwargs):
        return None

    def no_unemployment(*_args, **_kwargs):
        return None

    def no_county(*_args, **_kwargs):
        return None

    def blocked_http(*_args, **_kwargs):
        raise OfflineSDOHNetworkError(
            "External SDOH HTTP access is disabled for this Disco Inferno worker."
        )

    # Public SDOH entry points.
    sdoh_module.get_air_quality_by_zip = no_air_quality
    sdoh_module.get_poverty_pct_by_zcta = no_poverty
    if hasattr(sdoh_module, "get_places_measure_by_zcta"):
        sdoh_module.get_places_measure_by_zcta = no_places
    if hasattr(sdoh_module, "get_unemployment_rate_by_zip"):
        sdoh_module.get_unemployment_rate_by_zip = no_unemployment
    if hasattr(sdoh_module, "zip_to_county_fips"):
        sdoh_module.zip_to_county_fips = no_county

    # Lower-level network helpers are disabled too so a future SDOH code path
    # cannot silently bypass the public wrappers.
    if hasattr(sdoh_module, "_airnow_observation"):
        sdoh_module._airnow_observation = no_air_quality
    if hasattr(sdoh_module, "_http_get_json_with_retries"):
        sdoh_module._http_get_json_with_retries = lambda *_args, **_kwargs: None

    # build_adt imports these functions directly into hl7_demo.messages, so its
    # aliases must be replaced as well as the originals in hl7_demo.sdoh.
    hl7_messages.get_air_quality_by_zip = no_air_quality
    hl7_messages.get_poverty_pct_by_zcta = no_poverty

    # Replace only the SDOH module's references to requests/time. The actual
    # requests and time modules remain untouched for the rest of the worker.
    sdoh_module.requests = SimpleNamespace(get=blocked_http)
    sdoh_module.time = SimpleNamespace(sleep=lambda *_args, **_kwargs: None)
