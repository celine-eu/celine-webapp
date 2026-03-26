# celine/webapp/api/co2_settings.py
"""CO2 equivalent settings — GET /api/settings/co2.

Factors are sourced from national grid emission intensity databases.
kg_per_kwh: average CO2 emitted per kWh of grid electricity displaced by renewable production.
trees_per_ton: equivalent trees that absorb 1 tonne of CO2 per year (IPCC estimate ~21).
"""
import logging
import os

from fastapi import APIRouter

from celine.webapp.api.schemas import Co2LocaleSettings, Co2SettingsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# CO2 emission intensity by country (kg CO2eq per kWh, grid average)
# Sources: EEA, IEA, national grid operators (2023 data)
CO2_FACTORS: dict[str, dict] = {
    "it": {"country_name": "Italy",       "kg_per_kwh": 0.233, "trees_per_ton": 21.0},
    "es": {"country_name": "Spain",       "kg_per_kwh": 0.165, "trees_per_ton": 21.0},
    "fi": {"country_name": "Finland",     "kg_per_kwh": 0.085, "trees_per_ton": 21.0},
    "de": {"country_name": "Germany",     "kg_per_kwh": 0.350, "trees_per_ton": 21.0},
    "fr": {"country_name": "France",      "kg_per_kwh": 0.052, "trees_per_ton": 21.0},
    "pt": {"country_name": "Portugal",    "kg_per_kwh": 0.217, "trees_per_ton": 21.0},
    "gr": {"country_name": "Greece",      "kg_per_kwh": 0.301, "trees_per_ton": 21.0},
    "at": {"country_name": "Austria",     "kg_per_kwh": 0.117, "trees_per_ton": 21.0},
    "nl": {"country_name": "Netherlands", "kg_per_kwh": 0.275, "trees_per_ton": 21.0},
    "be": {"country_name": "Belgium",     "kg_per_kwh": 0.142, "trees_per_ton": 21.0},
    "pl": {"country_name": "Poland",      "kg_per_kwh": 0.681, "trees_per_ton": 21.0},
    "ro": {"country_name": "Romania",     "kg_per_kwh": 0.266, "trees_per_ton": 21.0},
}

_DEFAULT_COUNTRY = "it"


def _get_locale_settings(country_code: str) -> Co2LocaleSettings:
    data = CO2_FACTORS.get(country_code, CO2_FACTORS[_DEFAULT_COUNTRY])
    return Co2LocaleSettings(
        country_code=country_code if country_code in CO2_FACTORS else _DEFAULT_COUNTRY,
        country_name=data["country_name"],
        kg_per_kwh=data["kg_per_kwh"],
        trees_per_ton=data["trees_per_ton"],
    )


@router.get("/co2", response_model=Co2SettingsResponse)
async def co2_settings() -> Co2SettingsResponse:
    """Return CO2 equivalent factors for the configured locale and all available locales.

    The active country is controlled by the CO2_COUNTRY env var (default: it).
    """
    country_code = os.getenv("CO2_COUNTRY", _DEFAULT_COUNTRY).lower()
    current = _get_locale_settings(country_code)
    available = [
        Co2LocaleSettings(
            country_code=code,
            country_name=data["country_name"],
            kg_per_kwh=data["kg_per_kwh"],
            trees_per_ton=data["trees_per_ton"],
        )
        for code, data in CO2_FACTORS.items()
    ]
    return Co2SettingsResponse(current=current, available=available)
