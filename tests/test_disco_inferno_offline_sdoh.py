from __future__ import annotations

import pytest

from experiments.disco_inferno.offline_sdoh import (
    OfflineSDOHNetworkError,
    install_offline_sdoh,
)
from hl7_demo import messages as hl7_messages
from hl7_demo import sdoh as sdoh_module


def test_offline_sdoh_blocks_network_and_replaces_message_aliases():
    original = {
        "sdoh_requests": sdoh_module.requests,
        "sdoh_time": sdoh_module.time,
        "sdoh_air": sdoh_module.get_air_quality_by_zip,
        "sdoh_poverty": sdoh_module.get_poverty_pct_by_zcta,
        "messages_air": hl7_messages.get_air_quality_by_zip,
        "messages_poverty": hl7_messages.get_poverty_pct_by_zcta,
    }
    optional_names = [
        "get_places_measure_by_zcta",
        "get_unemployment_rate_by_zip",
        "zip_to_county_fips",
        "_airnow_observation",
        "_http_get_json_with_retries",
    ]
    for name in optional_names:
        if hasattr(sdoh_module, name):
            original[name] = getattr(sdoh_module, name)

    try:
        install_offline_sdoh()

        assert hl7_messages.get_air_quality_by_zip("02139") == {}
        assert hl7_messages.get_poverty_pct_by_zcta("02139") is None
        assert sdoh_module.get_air_quality_by_zip("02139") == {}
        assert sdoh_module.get_poverty_pct_by_zcta("02139") is None

        if hasattr(sdoh_module, "get_places_measure_by_zcta"):
            assert sdoh_module.get_places_measure_by_zcta("02139") is None
        if hasattr(sdoh_module, "get_unemployment_rate_by_zip"):
            assert sdoh_module.get_unemployment_rate_by_zip("02139") is None

        with pytest.raises(OfflineSDOHNetworkError):
            sdoh_module.requests.get("https://api.census.gov/")
    finally:
        sdoh_module.requests = original["sdoh_requests"]
        sdoh_module.time = original["sdoh_time"]
        sdoh_module.get_air_quality_by_zip = original["sdoh_air"]
        sdoh_module.get_poverty_pct_by_zcta = original["sdoh_poverty"]
        hl7_messages.get_air_quality_by_zip = original["messages_air"]
        hl7_messages.get_poverty_pct_by_zcta = original["messages_poverty"]
        for name in optional_names:
            if name in original:
                setattr(sdoh_module, name, original[name])
