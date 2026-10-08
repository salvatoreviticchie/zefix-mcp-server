# Zefix MCP Server

An [MCP](https://modelcontextprotocol.io) server that lets AI agents look up Swiss companies
in **Zefix**, the Central Business Name Index of the Federal Registry of Commerce.

It runs over **streamable HTTP**, so remote agents (for example a Salesforce Agentforce agent)
can call it as well as local MCP clients.

## Tools

| Tool | What it does |
|---|---|
| `search_companies` | Find companies by name. Optional filters: canton (`VD`, `GE`, `ZH`…), active only, max results (1–50), language. Returns name, UID, legal form, seat, status and a Zefix link. |
| `get_company` | Full register entry for one company by UID (`CHE-123.456.789`, punctuation optional): legal form, status, address, purpose, capital, translated names, auditors, last publication date and links to Zefix and the cantonal excerpt. |

Both tools accept `language` = `en`, `de`, `fr` or `it` for legal form names and links.

Errors come back as `{"error": "..."}` with a readable message, and "not found" is reported
explicitly instead of as an empty result, so the agent can explain what happened.

## Requirements

- Python 3.10+
- A Zefix PublicREST account (free). Request one from the Federal Registry of Commerce via
  [zefix.admin.ch](https://www.zefix.admin.ch/).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

export ZEFIX_USER="..."
export ZEFIX_PASSWORD="..."

.venv/bin/python zefix_server.py
```

The MCP endpoint is then `http://127.0.0.1:8000/mcp`. Set `HOST` and `PORT` to change it
(use `HOST=0.0.0.0` inside a container). See `.env.example` for all variables.

## Try it with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector --transport http --server-url http://127.0.0.1:8000/mcp
```

## Design notes

- **Stateless HTTP with JSON responses**: every request stands alone, which suits serverless
  and container hosting.
- **Input validation before any API call**: invalid cantons, UIDs or languages are rejected
  locally, so Zefix is never called with bad input.
- **Gentle on Zefix**: results are capped at 50 and requests time out after 15 seconds.
  Zefix shares its infrastructure with the public website, so please don't use this server
  for bulk extraction.

## Data source and terms

Data: **Zefix PublicREST API, Federal Registry of Commerce (FRC)**, published under
[OGD open use, source must be provided](https://opendata.swiss/en/terms-of-use#terms_by).

Every tool response includes a `source` field stating the origin and that the data was
reformatted, as the Zefix terms require. Zefix data has no legal effect; for legally binding
information, use the official cantonal register excerpt (`cantonal_excerpt_url`).

## Security

This server has **no authentication of its own yet**. Run it locally only, or behind an
authenticated gateway: anyone who can reach the endpoint uses your Zefix account.

## License

Code: [MIT](LICENSE). Zefix data remains subject to the Zefix terms above.
