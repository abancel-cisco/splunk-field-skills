---
name: splunk-itsi-api-access
category: itsi
description: Access a Splunk ITSI Search Head over REST API. Covers prerequisites a Splunk admin must arrange (IP allowlist, dedicated REST tokens), JWT vs MCP token shapes, capabilities needed, 401 troubleshooting, common endpoint cheatsheet (itoa_interface/event_management_interface), search jobs oneshot vs async dispatches, notable event index gotchas, proxy egress configuration for loopback/internal subnets, and a shell helper template.
disable-model-invocation: true
---

# Splunk ITSI REST API Access

How to get a Splunk ITSI Search Head reachable over REST from your machine, with a token that actually works, and the diagnostic shortcuts for the most common failure modes.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use this skill

- Setting up REST access to a Splunk ITSI Search Head (Cloud or on-prem) for the first time
- You have been handed a "token" and you get `401 call not properly authenticated`
- A `curl` to `:8089` times out — diagnosing whether it's the network or auth
- Bootstrapping a shell helper for repeated REST calls
- Designing a project's prerequisites list to send to the Splunk admin
- The user mentions ITSI API, itoa_interface, SA-ITOA, MCP token vs API token

## Prerequisites the Splunk admin must arrange

This is the email you send before you touch anything. Get all five before promising you can do API work:

1. **URL of the ITSI SH on port 8089.** Splunk Cloud format: `https://<stack>.splunkcloud.com:8089`. The stack name is the same one used in the Web UI URL minus the protocol, port, and path.
2. **IP allowlist entry for your egress IP** (or VPN range). Splunk Cloud ships with the management port behind an allowlist; without your IP in there, every curl will time out, not 401. Verify your IP with `curl -s ifconfig.me` and send that exact value.
3. **A dedicated REST API token** — *not* an MCP token, not a session key. See the next section for why this matters. Ask the Splunk admin to create it via `Settings → Tokens → New Token` with audience like `cursor-api-access`, expiration `+90d` or `Never` per their policy.
4. **A user account with the right capabilities** — see the capabilities section. If the token is bound to a user who doesn't have `write_itsi_service`, your CRUD calls will fail with 403 even though auth succeeds.
5. **A safe sandbox naming convention** (you bring this, not them) — see the related skill `splunk-itsi-service-tree-design` for the SANDBOX-* prefix pattern that protects production trees during exploration.

## Token types — the JWT vs MCP gotcha

There are at least three flavors of "token" floating around Splunk and they are not interchangeable. Recognize them by shape:

| Token type | Shape | Length | Use case | Works for REST? |
|---|---|---|---|---|
| **Splunk Authentication Token (JWT, modern)** | `eyJraWQi...{header}.{payload}.{sig}` — 3 base64 segments separated by `.` | ~700-800 chars | The right one. Created via `Settings → Tokens`. | **YES** |
| **MCP-bound token** (created with `aud=MCP server` or via the `mcp-remote` helper) | Looks like a Splunk JWT but the `aud` claim restricts it to the MCP endpoint | ~700-800 chars | Only works against `/services/mcp` | **NO** — 401 on every other endpoint |
| **Legacy session key / old REST token** | Single string with `==` base64 padding, often with a single `.` somewhere | ~600-700 chars | Older REST integrations | Sometimes — depends on version |

Decoding a JWT to check what it's good for (no signature verification needed):

```python
import base64, json
def b64decode(seg): 
    pad = '=' * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)
header, payload, _sig = token.split('.')
print(json.loads(b64decode(header)))   # confirms it's a JWT
print(json.loads(b64decode(payload)))  # check 'aud' claim — "Cursor API access" good, "MCP server" bad
```

The trip-wire: an admin who has only ever issued MCP tokens for Cursor will often hand you the MCP token because it's labeled "Cursor". Always read the `aud` claim before debugging connectivity.

## Capabilities you actually need

For service-tree work via `/itoa_interface/service`:

| Capability | Needed for | If missing |
|---|---|---|
| `read_itsi_service` | GET on services | 403 on reads |
| `write_itsi_service` | POST (create + update) | 403 on writes |
| `delete_itsi_service` | DELETE | 403 on deletes |
| `configure_itsi_service` | Some advanced service config (templates, dependencies in bulk) | Partial 403s on edge cases |
| `itoa_admin` (role, not a capability) | Cross-team service access, KPI base searches | Limited visibility |

Verify your token's actual caps in one call:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/services/authentication/current-context?output_mode=json" \
| python3 -c "
import sys,json
d = json.load(sys.stdin)['entry'][0]['content']
print('username:', d['username'])
print('roles   :', d.get('roles', []))
print('caps    :', len(d.get('capabilities', [])))
for need in ['read_itsi_service','write_itsi_service','delete_itsi_service']:
    print(f'  {need:30s} {\"YES\" if need in d.get(\"capabilities\",[]) else \"MISSING\"}')
"
```

A user with the `itoa_admin` role typically gets ~508 capabilities including all three above. If the count is much lower, the token is bound to a more restricted account.

## Connectivity diagnostic ladder

When something fails against `:8089`, work through these in order. The HTTP code (or its absence) tells you exactly where to go next:

| Symptom | Cause | Fix |
|---|---|---|
| `curl: (28) Connection timed out` | IP not in allowlist | Send your egress IP to the Splunk admin |
| `curl: (60) SSL certificate problem` | On-prem SH with self-signed cert | Add `-k` for testing only; for prod, install the CA |
| `HTTP=303 See Other` against `https://<stack>.splunkcloud.com/...` (no port) | You hit the web UI port (443) instead of management (8089) | Use `:8089` explicitly; the web port redirects authenticated REST through `splunkd/__raw` which has its own quirks |
| `HTTP=401 call not properly authenticated` (with `Bearer`) | Token rejected. Try `Splunk` scheme as a quick check, then check token shape | If `Splunk` also 401s, the token is invalid/expired/wrong audience. Go back to "Token types" |
| `HTTP=401` with `Authorization: Splunk <token>` but `Bearer` works | Token is JWT — `Bearer` is the right scheme. Code path that uses `Splunk` is legacy | Use `Bearer` consistently |
| `HTTP=403` after auth succeeds | Capability gap | Check `current-context` for missing capabilities |
| `HTTP=500` with `bad character in reply size` | Splunk's web proxy is mangling chunked encoding through `splunkd/__raw` | Use `:8089` direct, not the `/en-US/splunkd/__raw/services/...` path |
| `HTTP=200` but `entry` is empty | You hit a `/services/` endpoint that returns wrapped JSON; ITSI's `/itoa_interface/` returns raw arrays | Check the response shape (array vs `{entry: [...]}`) |

## REST endpoint cheatsheet

Three URL families. Different conventions for body format, response shape, and pagination.

### 1. Core Splunk REST (`/services/*`)

Returns `{entry: [{name, content: {...}}, ...], paging: {...}}` wrapper. Body usually form-encoded.

```
GET  /services/server/info                         - Splunk version, build, roles, OS
GET  /services/authentication/current-context      - identity + roles + capabilities for THIS token
GET  /services/apps/local                          - installed apps (filter on name)
GET  /services/authentication/users                - users (needs admin caps)
POST /services/auth/login                          - get a session key with user/pass (avoid in favor of tokens)
POST /services/search/jobs                         - run a search (returns sid)
GET  /services/search/jobs/<sid>/results          - get search results
```

### 2. ITSI REST — Service Tree & Config (`/servicesNS/nobody/SA-ITOA/itoa_interface/*`)

Returns raw JSON array (no `entry` wrapper). Body must be JSON (set `Content-Type: application/json`). `nobody` is the user context; `SA-ITOA` is the app namespace.

```
GET    /itoa_interface/service                    - list services (count default 30; use count=300)
GET    /itoa_interface/service/<key>              - read one
POST   /itoa_interface/service                    - create (no body _key) - returns {_key: <uuid>}
POST   /itoa_interface/service/<key>              - update (full replacement)
POST   /itoa_interface/service/<key>?is_partial_data=1  - PATCH (only fields you pass)
DELETE /itoa_interface/service/<key>              - delete (irreversible, returns 204)

GET    /itoa_interface/team                       - teams (sec_grp)
GET    /itoa_interface/kpi_base_search            - base searches (for KPI templates)
GET    /itoa_interface/entity                     - entities
GET    /itoa_interface/entity_type                - entity types
GET    /itoa_interface/service_template           - service templates
GET    /itoa_interface/notable_event_aggregation_policy  - episode policies
GET    /itoa_interface/deep_dive                  - saved deep dives
```

### 3. ITSI REST — Episode Management (`/servicesNS/nobody/SA-ITOA/event_management_interface/*`)

Handles Event Analytics / Episode CRUD operations. Returns raw JSON array. Body must be JSON. Key represents `itsi_group_id`.

```
GET    /event_management_interface/notable_event_group           - list episodes (use filter for specific criteria)
GET    /event_management_interface/notable_event_group/<key>     - read one episode
POST   /event_management_interface/notable_event_group/<key>?is_partial_data=1 - update status, severity, owner
```

Filter shortcut (URL-encoded JSON in the `filter` param):

```bash
# Get only the service whose title is "Invoicing"
curl -G "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service" \
  --data-urlencode 'filter={"title":"Invoicing"}' \
  --data-urlencode 'output_mode=json' \
  --data-urlencode 'fields=title,_key' \
  -H "Authorization: Bearer $TOKEN"

# Get only the episode whose ID matches _key
curl -G "$URL/servicesNS/nobody/SA-ITOA/event_management_interface/notable_event_group" \
  --data-urlencode 'filter={"_key":"fd1e636f-4cf5-499c-a161-c059b2408858"}' \
  --data-urlencode 'output_mode=json' \
  -H "Authorization: Bearer $TOKEN"
```

## Payload format conventions

| Endpoint family | Content-Type | Body shape | Example |
|---|---|---|---|
| `/services/*` (core Splunk) | `application/x-www-form-urlencoded` | `key=value&key=value` | `name=foo&disabled=1` |
| `/services/<endpoint>?output_mode=json` | same | same | adds JSON response wrapping only |
| `/servicesNS/.../itoa_interface/*` | `application/json` | Raw JSON object | `{"title":"X","sec_grp":"default_itsi_security_group"}` |
| `/servicesNS/.../event_management_interface/*` | `application/json` | Raw JSON object | `{"status":"4","owner":"daniel"}` |
| ITSI partial update | `application/json` | Subset of fields + query string `?is_partial_data=1` | `{"status": "4"}` |

Pitfall: posting JSON to `/services/*` returns 200 with empty body but doesn't actually update anything. Always use form-encoding for `/services/*`, JSON for ITSI interfaces.

## Splunk Search jobs via REST API

### 1. Synchronous Search via Oneshot (Recommended)
To run a search synchronously and get results in a single HTTP request, use the `/services/search/jobs/oneshot` endpoint via a `POST` request. Ensure the payload is form-encoded:

```bash
curl --location -X POST 'https://<stack>.splunkcloud.com:8089/services/search/jobs/oneshot?output_mode=json' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'search=search index=itsi_tracked_alerts itsi_group_id="fd1e636f-4cf5-499c-a161-c059b2408858"'
```

### 2. The Search Job GET Pitfall
* **Symptom:** Dispatches returns empty lists or doesn't execute searches.
* **Explanation:** Sending a `GET` request with a `search` query parameter to `/services/search/jobs` lists currently running or saved search jobs matching that search string. It **does not** run a new search. To run a search asynchronously, you must `POST` to `/services/search/jobs` to create a job (which returns a search ID `sid`), wait for it to complete, and then `GET` the results from `/services/search/jobs/<sid>/results`.

### 3. Notable Event Index Gotcha
* In ITSI, notable events are stored in **`index=itsi_tracked_alerts`**.
* The index **`notable`** is used by Enterprise Security (ES) and will return 0 results on a dedicated ITSI search head.

## Proxy Egress & Local Subnet Routing

* **Local Egress Bypass (`splunk-launch.conf`):** Custom python search commands (like `earemotesearch`) run inside separate python processes. They ignore `server.conf` proxy settings and check standard OS environment variables. To bypass the proxy for local Search Head loopbacks, add the Search Head's hostname to the `no_proxy`/`NO_PROXY` environment variables in `splunk-launch.conf`.
* **Outbound Webhooks / Internal VLANs:** Webhooks pointing to local/internal IP addresses (like internal ticketing gateways on the same subnets) must also be bypassed in `splunk-launch.conf`. If not, python routes the webhook requests to the outbound egress proxy, resulting in connection timeouts (`Errno 110`).

## 401 troubleshooting flow

```
401 call not properly authenticated
├── Is connectivity OK? (curl reaches the SH, gets a response)
│   └── No -> back to "Connectivity diagnostic ladder"
├── Is the token a JWT (3 parts, starts with eyJ)?
│   ├── Yes -> decode the payload (no signature needed):
│   │       - aud == "MCP server"? -> wrong token type, ask for an API token
│   │       - exp in the past?     -> expired, ask for a fresh one
│   │       - sub == expected user? -> if not, wrong account
│   └── No -> legacy token, may need Authorization: Splunk <token> scheme
├── Try BOTH schemes on /services/server/info:
│       curl -H "Authorization: Bearer $TOKEN" ...
│       curl -H "Authorization: Splunk $TOKEN" ...
│   └── Both 401 -> token is invalid/revoked
└── One scheme returns 200 -> use that scheme going forward
```

## Shell helper template

Wrap REST access in a single command so day-2 work is one-liner rather than a curl paragraph. Save at `~/.cursor/scripts/itsi`:

```bash
#!/usr/bin/env bash
# itsi - Splunk ITSI REST helper. Reads token + URL from ~/.cursor/<env_file>.
set -euo pipefail

ENV_FILE="${ITSI_ENV_FILE:-$HOME/.cursor/itsi.env}"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

: "${ITSI_TOKEN:?ITSI_TOKEN not set (source $ENV_FILE)}"
: "${ITSI_URL:?ITSI_URL not set}"

cmd="${1:-help}"
shift || true

H_AUTH=(-H "Authorization: Bearer $ITSI_TOKEN")
H_JSON=(-H "Content-Type: application/json")

case "$cmd" in
  help|-h|--help)
    grep '^# ' "$0" | sed 's/^# \{0,1\}//'
    cat <<-EOF
		Commands:
		  whoami             - identity + roles + capability count
		  health             - server info (version, build, roles)
		  get <path>         - GET <URL><path>?output_mode=json (path includes leading /)
		  post <path> [json] - POST raw JSON body
		  services           - list ITSI services (count=300, title + key + dep counts)
		  service <title>    - get one service by exact title match
	EOF
    ;;
  whoami)
    curl -sS --max-time 15 "${H_AUTH[@]}" \
      "$ITSI_URL/services/authentication/current-context?output_mode=json" \
    | python3 -c "import sys,json;d=json.load(sys.stdin)['entry'][0]['content'];print(f\"user: {d['username']}\\nroles: {d.get('roles',[])}\\ncaps : {len(d.get('capabilities',[]))}\")"
    ;;
  health)
    curl -sS --max-time 15 "${H_AUTH[@]}" \
      "$ITSI_URL/services/server/info?output_mode=json" \
    | python3 -c "import sys,json;c=json.load(sys.stdin)['entry'][0]['content'];print(f\"server : {c['serverName']}\\nversion: {c['version']}  build={c['build']}\\nroles  : {c.get('server_roles',[])}\")"
    ;;
  get)
    [ -z "${1:-}" ] && { echo "usage: itsi get <path>"; exit 2; }
    curl -sS --max-time 30 "${H_AUTH[@]}" "$ITSI_URL$1" | python3 -m json.tool
    ;;
  post)
    [ -z "${1:-}" ] && { echo "usage: itsi post <path> [json_body]"; exit 2; }
    path="$1"; shift
    body="${1:-{}}"
    curl -sS --max-time 30 "${H_AUTH[@]}" "${H_JSON[@]}" -X POST -d "$body" "$ITSI_URL$path" | python3 -m json.tool
    ;;
  services)
    curl -sS --max-time 30 "${H_AUTH[@]}" \
      "$ITSI_URL/servicesNS/nobody/SA-ITOA/itoa_interface/service?count=300&fields=title,_key,services_depends_on,services_depending_on_me&output_mode=json" \
    | python3 -c "
import sys,json
d=json.load(sys.stdin); items=d if isinstance(d,list) else d.get('entry',[])
for s in sorted(items, key=lambda x: x.get('title','')):
    print(f\"  {s.get('title','')[:50]:50s} down={len(s.get('services_depends_on') or []):>2d} up={len(s.get('services_depending_on_me') or []):>2d}\")
print(f'\\n  {len(items)} services')
"
    ;;
  service)
    [ -z "${1:-}" ] && { echo "usage: itsi service <title>"; exit 2; }
    curl -sS --max-time 15 "${H_AUTH[@]}" -G "$ITSI_URL/servicesNS/nobody/SA-ITOA/itoa_interface/service" \
      --data-urlencode "filter={\"title\":\"$1\"}" --data-urlencode 'output_mode=json' \
    | python3 -m json.tool
    ;;
  *)
    echo "Unknown command: $cmd"
    "$0" help
    exit 64
    ;;
esac
```

Make it executable (`chmod +x ~/.cursor/scripts/itsi`) and add the dir to `PATH`. Then `itsi whoami`, `itsi services`, `itsi get /services/server/info` etc. all become one-liners.

CRLF caveat (lesson from Friday's `o11y` helper): if you ever edit the script on Windows/web and save it back, line endings become CRLF and bash will fail with `env: bash\r: No such file or directory`. Fix:

```bash
python3 -c "p='$HOME/.cursor/scripts/itsi'; open(p,'wb').write(open(p,'rb').read().replace(b'\r',b''))"
```

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Using an MCP token for REST and blaming connectivity for the 401 | Wastes hours; the token is technically valid but scoped wrong | Always decode JWT payload and check `aud` claim before troubleshooting connectivity |
| Hitting `https://<stack>.splunkcloud.com/services/...` (port 443) for REST | Returns 303 or goes through `splunkd/__raw` web proxy which mangles bodies | Use `:8089` direct |
| Storing the token in `.zshrc` or any always-shell-loaded file with `chmod 644` | Anyone with file read on your machine has it | Put in a dedicated `.env` file at `~/.cursor/<environment>.env` with `chmod 600`, source on demand |
| Pasting the token into chat/Slack/email | Leaks into transcripts and indexed search | If you must, mark for rotation, treat as compromised at the end of the project, and never use in prod |
| Adding `-k` (insecure SSL) reflexively for Splunk Cloud | Splunk Cloud uses real certs; `-k` masks misconfiguration | Only `-k` for on-prem self-signed; for cloud, fix root cause if cert fails |
| Mixing JSON body with `/services/*` form endpoints | Returns 200 with empty body; silent no-op | JSON for `/itoa_interface/*`, form for `/services/*` |
| Polling `/itoa_interface/service` with no `count` parameter | Default is 30 — you'll think a service is missing when it's just past the first page | Always pass `count=300` (or higher) when discovering |

## Related skills

- `splunk-itsi-service-tree-design` — using REST to design and safely build a service tree (this skill = the rails; that skill = the route)
- `otel-vs-splunk-ingestion` — for the data side; ITSI is consuming what OTel produces

Once you hold a token, treat it as a credential for its whole life. Keep it in a secret
store or an environment variable rather than a tracker or a shared document, mask it in
chat and screenshots, and rotate it when the engagement ends or anyone leaves the project.
