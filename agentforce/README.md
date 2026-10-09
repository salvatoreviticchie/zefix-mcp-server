# Agentforce agent for the Zefix MCP server

A Salesforce **Agentforce Employee Agent**, written in Agent Script, that answers questions
about Swiss companies by calling this repo's MCP server through the **Agentforce Registry**.

```
User ─► Agentforce agent ─► Agentforce Registry ─(OAuth 2.0, client credentials)─► Zefix MCP server ─► Zefix API
```

Example: *"Find Migros Bank in Zurich and give me its address and legal form."*
The agent calls `search_companies`, then `get_company`, and answers with the legal form,
address, cantonal excerpt link and the Zefix source line.

## Contents

| Path | What it is |
|---|---|
| `force-app/main/default/aiAuthoringBundles/Swiss_Company_Assistant/` | The agent: `.agent` script (instructions, actions) and bundle metadata |
| `sfdx-project.json` | Salesforce DX project (API version 67.0) |

## Prerequisites

- A Salesforce org with Agentforce (a Developer Edition org works) and the `sf` CLI.
- The MCP server deployed over HTTPS with OAuth (see the [main README](../README.md)).

## Setup

**1. Register the MCP server** in Setup → **Agentforce Registry** → New:
URL `https://<your-host>/mcp`, authentication **OAuth 2.0**, Identity Provider URL = your
token endpoint (Auth0: `https://<tenant>/oauth/token`), client ID/secret of the M2M app,
scope `zefix:read`.

> **Auth0:** set the tenant's **Default Audience** to your API identifier
> (Settings → General → API Authorization Settings). The Registry form has no audience
> field, and without a default audience Auth0 won't issue a usable JWT.

**2. Activate the tools and get their IDs**

```bash
sf agent mcp list -o <org> --json                 # find the server ID (0Le...)
sf agent mcp fetch -i <server-id> -o <org> --json # tool names, descriptions, status
```

Activate both tools with `sf agent mcp asset replace` (see "Lessons learned" below), then note
each tool's asset ID (`1XO...`) from the response.

**3. Point the agent at your tool IDs.** In `Swiss_Company_Assistant.agent`, replace the two
`mcpTool://1XO...` targets with your own IDs. The IDs in this file belong to the author's org.

**4. Deploy, publish, activate**

```bash
sf agent validate authoring-bundle --json --api-name Swiss_Company_Assistant
sf project deploy start --json --metadata AiAuthoringBundle:Swiss_Company_Assistant -o <org>
sf agent publish authoring-bundle --json --api-name Swiss_Company_Assistant -o <org>
sf agent activate --json --api-name Swiss_Company_Assistant -o <org>
```

**5. Test it** in Agentforce Builder's Preview panel, or in the terminal:

```bash
sf agent preview --api-name Swiss_Company_Assistant -o <org>
```

On a free host that sleeps when idle, call `/health` first so the first tool call doesn't time out.

## Lessons learned (MCP tools in Agent Script)

These behaviours were observed with `sf` CLI 2.113 and API 67.0 and were not obvious from the
documentation at the time:

1. **The action target is the tool's asset ID, not its name.**
   `target: "mcpTool://1XO..."` works; `mcpTool://ServerName__tool_name` fails at publish with
   *"The MCP action ... has an invalid target ID value"*.
2. **Don't declare `inputs:` or `outputs:` on `mcpTool` actions.** Salesforce takes the
   parameters from the MCP server's input schema. Declaring them makes publish fail with
   *"An error occurred when processing the &lt;Entity&gt; entity"*. `description`, `label`
   and `target` are enough.
3. **Activating tools needs proof you reviewed them.** `sf agent mcp asset replace` requires each
   active tool's `description` (the CLI drops `serverFingerprint`). Send the description
   *HTML-unescaped*: `fetch` returns `&quot;` and similar, and the escaped text is rejected as
   *"doesn't match current remote state"*.
4. **New SFDX projects may default to an older API version** (64.0), and deploying an
   `AiAuthoringBundle` then fails with *"Not available for deploy for this API version"*.
   Set `sourceApiVersion` to `67.0` or later.
5. **An Employee Agent needs no Einstein Agent User**, unlike a Service Agent, so it's the
   simplest type for internal tools and demos.
