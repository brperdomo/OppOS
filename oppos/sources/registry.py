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

    # --- SAP/Ariba states (4) ---
    from oppos.sources.platforms.sap_ariba import SITES as s_sites, fetch_opportunities as s_fetch
    for key, site in s_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(s_fetch, site))

    # --- PROACTIS/WebProcure states (3) ---
    from oppos.sources.platforms.proactis import SITES as pr_sites, fetch_opportunities as pr_fetch
    for key, site in pr_sites.items():
        _REGISTRY[key] = (f"{site.name} ({site.state})", _bind(pr_fetch, site))

    # --- PA eMarketplace (custom ASP.NET site, not JAGGAER) ---
    from oppos.sources.platforms.pa_emarketplace import fetch_opportunities as pa_fetch
    _REGISTRY["pennsylvania_emarketplace"] = ("PA eMarketplace (PA)", pa_fetch)

    # --- Starbridge RFP aggregator ---
    from oppos.sources.starbridge import fetch_opportunities as sb_fetch
    _REGISTRY["starbridge"] = ("Starbridge (RFP Aggregator)", sb_fetch)

    # --- Private sector sources ---
    from oppos.sources.google_cse import fetch_opportunities as gcse_fetch
    _REGISTRY["google_cse"] = ("Google CSE (Private Sector)", gcse_fetch)

    from oppos.sources.target_accounts import fetch_opportunities as ta_fetch
    _REGISTRY["target_accounts"] = ("Target Accounts (Private Sector)", ta_fetch)

    return _REGISTRY


def get_enabled_sources() -> list[tuple[str, str, FetchFn]]:
    """Returns [(source_key, display_name, fetch_fn)] for all enabled sources."""
    registry = _load_registry()
    enabled = []
    for key in ENABLED_SOURCES:
        if key == "all_states":
            for k, (name, fn) in registry.items():
                if k != "sam_gov":
                    enabled.append((k, name, fn))
            continue
        if key in registry:
            name, fn = registry[key]
            enabled.append((key, name, fn))
        else:
            logger.warning("Unknown source '%s' in ENABLED_SOURCES — skipping", key)
    return enabled


def list_available() -> list[tuple[str, str]]:
    """Returns [(source_key, display_name)] for all registered sources."""
    registry = _load_registry()
    return [(k, v[0]) for k, v in sorted(registry.items())]
