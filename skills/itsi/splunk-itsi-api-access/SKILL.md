---
name: splunk-itsi-api-access
category: itsi
description: Work with Splunk ITSI over its REST API once you can reach the stack - the capabilities ITSI calls need, the endpoint cheatsheet (itoa_interface, event_management_interface, KV store collections), payload and response-shape conventions, search jobs oneshot vs async, notable event index gotchas, and a shell helper template. Getting onto the stack in the first place - MCP vs API, tokens, allowlist, 401s and timeouts - is splunk-stack-access-mcp-vs-api.
disable-model-invocation: true
---

# Splunk ITSI REST API

What to call, with which rights, once an agent can reach the ITSI search head. Getting there
— MCP or API, the token, the allowlist, 401s and timeouts — is
`splunk-stack-access-mcp-vs-api`.

**Validated on:** ITSI 4.21.x. Read paths (`current-context`, `server/info`, `apps/local`,
`itoa_interface/service` GET) confirmed on ITSI 5.0.2 and Splunk Cloud 10.5.2605, 2026-10.
Writes not re-verified on 5.0.

## When to use this skill

- Creating or changing ITSI objects over REST: services, KPIs, entities, episodes
- A call succeeds on auth but returns 403 — a capability gap
- Working out which ITSI endpoint family to use and what it returns
- Bootstrapping a shell helper for repeated ITSI REST calls
- The user mentions ITSI API, itoa_interface, SA-ITOA

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

Check the three by name, as the snippet does. The total count is not a signal: an `sc_admin` token on a Splunk Cloud ITSI search head reported 336 capabilities while holding all three, against 490 for the same user on the primary search head.

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
| Treating the UI's "Token ID" as something you can turn back into a token | It's the `jti` claim; the value is unrecoverable once the creation dialog closes | Save the token at creation; use `jti` only to *identify* a token you already hold |
| Assuming a token can be reissued on demand at the end of a project | On a SAML stack reissue can be blocked for days pending a config change | Check expiry early, renew before it lapses, and record the expiry date alongside the token |

## Related skills

- `splunk-stack-access-mcp-vs-api` — MCP vs API, tokens, allowlist, connectivity and 401 diagnostics
- `splunk-itsi-service-tree-design` — using REST to design and safely build a service tree (this skill = the rails; that skill = the route)
- `otel-vs-splunk-ingestion` — for the data side; ITSI is consuming what OTel produces

Once you hold a token, treat it as a credential for its whole life. Keep it in a secret
store or an environment variable rather than a tracker or a shared document, mask it in
chat and screenshots, and rotate it when the engagement ends or anyone leaves the project.
