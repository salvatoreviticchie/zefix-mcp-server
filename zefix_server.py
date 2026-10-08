"""
Zefix MCP server: look up Swiss companies in the Central Business Name Index.

Exposes two tools over MCP (streamable HTTP):
    search_companies  find companies by name, optionally filtered by canton
    get_company       full register entry for one company, by UID

Data source: Zefix PublicREST API (Federal Registry of Commerce),
https://www.zefix.admin.ch/ZefixPublicREST/  — free, needs an account.

Setup:
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Environment variables (never hard-code them):
    ZEFIX_USER, ZEFIX_PASSWORD   Zefix API account (required)
    HOST                         default 127.0.0.1 (use 0.0.0.0 in a container)
    PORT                         default 8000 (most hosts set this for you)

Run:
    .venv/bin/python zefix_server.py      # MCP endpoint: http://HOST:PORT/mcp
"""

import os
import re

import httpx
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    "zefix",
    instructions=(
        "Look up companies in the Swiss commercial register (Zefix). "
        "Use search_companies to find a company by name, then get_company "
        "with its UID for details. Always mention the source to the user."
    ),
)

BASE_URL = "https://www.zefix.admin.ch/ZefixPublicREST/api/v1"
USER = os.environ.get("ZEFIX_USER", "")
PASSWORD = os.environ.get("ZEFIX_PASSWORD", "")
TIMEOUT_SECONDS = 15

# Zefix terms: the origin must be indicated, and any modification of the data too.
SOURCE = (
    "Zefix – Swiss Central Business Name Index, Federal Registry of Commerce "
    "(zefix.admin.ch). Reformatted and shortened; no legal effect."
)

CANTONS = {
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU", "NE",
    "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
}
LANGUAGES = {"en", "de", "fr", "it"}
MAX_RESULTS_LIMIT = 50  # be gentle: Zefix shares infrastructure with its public website


class ZefixError(Exception):
    """Raised by call_zefix; the message is safe to show to the user.

    Like a custom exception class in Apex (class ZefixException extends Exception).
    """


async def call_zefix(method: str, path: str, payload: dict | None = None) -> list:
    """Shared helper: call the Zefix API and return its JSON (always a list).

    Like a private Apex method doing the HTTP callout. It raises ZefixError
    instead of returning an error dict, so each tool decides what to say.
    """
    if not USER or not PASSWORD:
        raise ZefixError("Zefix credentials not configured. Set ZEFIX_USER and ZEFIX_PASSWORD.")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, auth=(USER, PASSWORD)) as client:
            response = await client.request(method, f"{BASE_URL}{path}", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise ZefixError(f"Zefix did not answer within {TIMEOUT_SECONDS} seconds.")
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            raise ZefixError("Zefix rejected the credentials (HTTP 401).")
        if status == 400:
            raise ZefixError("Zefix rejected the search parameters (HTTP 400).")
        raise ZefixError(f"Zefix returned HTTP {status}.")
    except httpx.RequestError as exc:
        raise ZefixError(f"Could not reach Zefix: {exc}")
    except ValueError:
        raise ZefixError("Zefix answered, but not with valid JSON.")


def normalize_uid(uid: str) -> str | None:
    """Accept 'CHE-107.028.276', 'che107028276', 'CHE 107 028 276' -> 'CHE107028276'."""
    digits = re.sub(r"[^0-9]", "", uid)
    if not uid.strip().upper().startswith("CHE") or len(digits) != 9:
        return None
    return f"CHE{digits}"


def format_uid(uid: str) -> str:
    """'CHE107028276' -> 'CHE-107.028.276' (the format people recognise)."""
    d = uid[3:]
    return f"CHE-{d[0:3]}.{d[3:6]}.{d[6:9]}"


def zefix_link(uid: str, language: str) -> str:
    return f"https://www.zefix.admin.ch/{language}/search/entity/list?name={uid}&directLink=true"


def legal_form_name(company: dict, language: str) -> str | None:
    names = (company.get("legalForm") or {}).get("name") or {}
    return names.get(language) or names.get("en")


@mcp.tool()
async def search_companies(
    name: str,
    canton: str | None = None,
    active_only: bool = True,
    max_results: int = 10,
    language: str = "en",
) -> dict:
    """Search the Swiss commercial register (Zefix) for companies by name.

    Use this first when the user names a company; then call get_company
    with the UID of the right match for full details.

    Args:
        name: Company name or part of it, e.g. "Nestlé" or "Migros Genossenschaft".
        canton: Optional two-letter canton code to filter on, e.g. "VD", "GE", "ZH".
        active_only: True (default) hides companies that were deleted from the register.
        max_results: How many matches to return, 1 to 50 (default 10).
        language: Language for legal form names and links: "en", "de", "fr" or "it".

    Returns a dict with: total_found, returned, companies (list of name, uid,
    legal_form, seat, status, zefix_url) and source.
    """
    name = name.strip()
    if len(name) < 2:
        return {"error": "The company name must be at least 2 characters."}
    if canton is not None:
        canton = canton.strip().upper()
        if canton not in CANTONS:
            return {"error": f"Unknown canton '{canton}'. Use a two-letter code like VD, GE or ZH."}
    if language not in LANGUAGES:
        return {"error": "Language must be one of: en, de, fr, it."}
    max_results = max(1, min(max_results, MAX_RESULTS_LIMIT))

    query = {"name": name, "activeOnly": active_only}
    if canton:
        query["canton"] = canton

    try:
        results = await call_zefix("POST", "/company/search", query)
    except ZefixError as exc:
        return {"error": str(exc)}

    if not results:
        return {"total_found": 0, "companies": [], "message": f"No company found for '{name}'.", "source": SOURCE}

    companies = [
        {
            "name": c.get("name"),
            "uid": format_uid(c["uid"]),
            "legal_form": legal_form_name(c, language),
            "seat": c.get("legalSeat"),
            "status": c.get("status"),
            "zefix_url": zefix_link(c["uid"], language),
        }
        for c in results[:max_results]
    ]
    return {
        "total_found": len(results),
        "returned": len(companies),
        "companies": companies,
        "source": SOURCE,
    }


@mcp.tool()
async def get_company(uid: str, language: str = "en") -> dict:
    """Get the full Swiss commercial register entry for one company.

    Args:
        uid: The company's UID, e.g. "CHE-107.028.276" (dots and dashes optional).
             Get it from search_companies if the user only gave a name.
        language: Language for legal form names and links: "en", "de", "fr" or "it".

    Returns a dict with: name, uid, legal_form, status, seat, canton, address,
    purpose, capital, translated_names, auditors, last_publication_date,
    deletion_date, zefix_url, cantonal_excerpt_url and source.
    """
    normalized = normalize_uid(uid)
    if normalized is None:
        return {"error": f"'{uid}' is not a valid Swiss UID. Expected format: CHE-123.456.789."}
    if language not in LANGUAGES:
        return {"error": "Language must be one of: en, de, fr, it."}

    try:
        results = await call_zefix("GET", f"/company/uid/{normalized}")
    except ZefixError as exc:
        return {"error": str(exc)}

    if not results:
        return {"error": f"No company found with UID {format_uid(normalized)}.", "source": SOURCE}

    c = results[0]
    address = c.get("address") or {}
    street = " ".join(filter(None, [address.get("street"), address.get("houseNumber")]))
    city = " ".join(filter(None, [address.get("swissZipCode"), address.get("city")]))
    capital = (
        f"{c['capitalNominal']} {c.get('capitalCurrency') or ''}".strip()
        if c.get("capitalNominal") else None
    )

    return {
        "name": c.get("name"),
        "uid": format_uid(c["uid"]),
        "legal_form": legal_form_name(c, language),
        "status": c.get("status"),
        "seat": c.get("legalSeat"),
        "canton": c.get("canton"),
        "address": ", ".join(filter(None, [address.get("careOf"), street, address.get("addon"),
                                           address.get("poBox"), city])) or None,
        "purpose": c.get("purpose"),
        "capital": capital,
        "translated_names": c.get("translation") or [],
        "auditors": [a.get("name") for a in c.get("auditCompanies") or []],
        "last_publication_date": c.get("sogcDate"),
        "deletion_date": c.get("deletionDate"),
        "zefix_url": (c.get("zefixDetailWeb") or {}).get(language) or zefix_link(c["uid"], language),
        "cantonal_excerpt_url": c.get("cantonalExcerptWeb"),
        "source": SOURCE,
    }


if __name__ == "__main__":
    # Streamable HTTP = the transport remote clients (like Agentforce) use.
    # stateless_http: every request stands alone, no server-side session — like
    # an Apex REST call. json_response: plain JSON replies instead of an SSE stream.
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        stateless_http=True,
        json_response=True,
    )
