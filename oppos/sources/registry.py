"""Source registry — maps source names to fetch functions.

Each state eProcurement portal is registered under its own key.
Platform scrapers are shared across states that use the same system.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from oppos.config import ENABLED_SOURCES

logger = logging.getLogger(__name__)

FetchFn = Callable[..., list[dict[str, Any]]]

_REGISTRY: dict[str, tuple[str, FetchFn]] = {}


def _bind(platform_fetch, site):
    """Create a zero-arg fetch function bound to a specific site config."""
    @functools.wraps(platform_fetch)
    def _wrapped(**kwargs):
        return platform_fetch(site, **kwargs)
    return _wrapped


def _load_registry() -> dict[str, tuple[str, FetchFn]]:
    if _REGISTRY:
        return _REGISTRY

    # --- Federal ---
    from oppos.sources.sam_gov import fetch_opportunities as sam_fetch
    _REGISTRY["sam_gov"] = ("SAM.gov (Federal)", sam_fetch)

    # --- Periscope/SOVRA states (7) ---
    from oppos.sources.platforms.periscope import SITES as p_sites, fetch_opportunities as p_fetch
    for key, site in p_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(p_fetch, site))

    # --- JAGGAER/SciQuest states (5) ---
    from oppos.sources.platforms.jaggaer import SITES as j_sites, fetch_opportunities as j_fetch
    for key, site in j_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(j_fetch, site))

    # --- CGI Advantage states (6) ---
    from oppos.sources.platforms.cgi_advantage import SITES as c_sites, fetch_opportunities as c_fetch
    for key, site in c_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(c_fetch, site))

    # --- PeopleSoft/Oracle states (7) ---
    from oppos.sources.platforms.peoplesoft import SITES as ps_sites, fetch_opportunities as ps_fetch
    for key, site in ps_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(ps_fetch, site))

    # --- Ivalua states (4) ---
    from oppos.sources.platforms.ivalua import SITES as i_sites, fetch_opportunities as i_fetch
    for key, site in i_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(i_fetch, site))

    # --- SAP/Ariba states ---
    from oppos.sources.platforms.sap_ariba import SITES as s_sites, fetch_opportunities as s_fetch
    for key, site in s_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(s_fetch, site))

    # --- Portals read through their own JSON endpoints (no browser needed) ---
    from oppos.sources.platforms.state_json import fetch_louisiana, fetch_mississippi, fetch_new_york, fetch_north_carolina
    _REGISTRY["new_york_nyscr"] = ("NYS Contract Reporter (NY)", lambda **kw: fetch_new_york())
    from oppos.sources.platforms.vendornet import fetch_opportunities as wi_fetch
    _REGISTRY["wisconsin_vendornet"] = ("VendorNet Wisconsin (WI)", lambda **kw: wi_fetch())
    _REGISTRY["mississippi_magic"] = ("MAGIC Mississippi (MS)", lambda **kw: fetch_mississippi())
    _REGISTRY["north_carolina_evp"] = ("NC eProcurement (NC)", lambda **kw: fetch_north_carolina())
    _REGISTRY["louisiana_lapac"] = ("LaPAC Louisiana (LA)", lambda **kw: fetch_louisiana())

    # --- PROACTIS/WebProcure states (3) ---
    from oppos.sources.platforms.proactis import SITES as pr_sites, fetch_opportunities as pr_fetch
    for key, site in pr_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(pr_fetch, site))

    # --- PA eMarketplace (custom ASP.NET site, not JAGGAER) ---
    from oppos.sources.platforms.pa_emarketplace import fetch_opportunities as pa_fetch
    _REGISTRY["pennsylvania_emarketplace"] = ("PA eMarketplace (PA)", pa_fetch)

    # --- Private sector sources ---
    from oppos.sources.google_cse import fetch_opportunities as gcse_fetch
    _REGISTRY["google_cse"] = ("Google CSE (Private Sector)", gcse_fetch)

    from oppos.sources.target_accounts import fetch_opportunities as ta_fetch
    _REGISTRY["target_accounts"] = ("Target Accounts (Private Sector)", ta_fetch)

    return _REGISTRY


# Why a source returns nothing (shown in Admin → Sources when a scan finds 0 listings). Kept current with the
# coverage audits; a source not listed here that returns 0 is worth a look.
SOURCE_NOTES: dict[str, str] = {
    "maryland_emma": "Needs a person to pass a reCAPTCHA check — OppOS can't read it. Check eMMA directly.",
    "alabama_alabamabuys": "Needs a person to pass a reCAPTCHA check — OppOS can't read it. Check the portal directly.",
    "ohio_ohiobuys": "Needs a person to pass a reCAPTCHA check — OppOS can't read it. Check the portal directly.",
    "north_dakota_ndbuys": "Needs a person to pass a reCAPTCHA check — OppOS can't read it. Check the portal directly.",
    "minnesota_swift": "Blocks automated access (bot protection). Check the portal directly.",
    "tennessee_edison": "Lists bids only after a supplier login.",
    "california_caleprocure": "Built on a system OppOS has no reader for yet.",
    "florida_mfmp": "Built on a system OppOS has no reader for yet.",
    "oklahoma_omes": "Built on a system OppOS has no reader for yet.",
    "wisconsin_vendornet": "Needs a headless browser: read by the daily scan on GitHub, not by a scan started inside the app.",
    "georgia_tgm": "Turns away automated requests with a browser check; reading it would mean imitating a browser (not done).",
    "arkansas_arbuy": "Had no open bids at the last check.",
    "colorado_vss": "Blocks automated browsers (\"Web Page Blocked\"). Check the portal directly.",
    "kentucky_emars": "Needs a headless browser: read by the daily scan on GitHub, not by a scan started inside the app.",
    "michigan_sigma": "Blocks automated browsers. Check the portal directly.",
    "alaska_iris": "Needs a headless browser: read by the daily scan on GitHub, not by a scan started inside the app.",
    "maine_vss": "The portal's page changed; OppOS's reader needs updating.",
    "west_virginia_wvoasis": "The portal's page changed; OppOS's reader needs updating.",
}

# Sources that are NOT state portals — excluded from "all_states" shortcut
_NON_STATE_SOURCES = frozenset({
    "sam_gov", "google_cse", "target_accounts",
})


def get_enabled_sources() -> list[tuple[str, str, FetchFn]]:
    """Returns [(source_key, display_name, fetch_fn)] for all enabled sources."""
    registry = _load_registry()
    enabled = []
    seen = set()
    for key in ENABLED_SOURCES:
        if key == "all_states":
            for k, (name, fn) in registry.items():
                if k not in _NON_STATE_SOURCES and k not in seen:
                    seen.add(k)
                    enabled.append((k, name, fn))
            continue
        if key in registry and key not in seen:
            seen.add(key)
            name, fn = registry[key]
            enabled.append((key, name, fn))
        elif key not in registry:
            logger.warning("Unknown source '%s' in ENABLED_SOURCES — skipping", key)
    return enabled


def list_available() -> list[tuple[str, str]]:
    """Returns [(source_key, display_name)] for all registered sources."""
    registry = _load_registry()
    return [(k, v[0]) for k, v in sorted(registry.items())]
