---
name: splunk-dashboard-studio-rest
category: platform
description: Create Splunk Dashboard Studio (v2) dashboards programmatically via the REST `data/ui/views` endpoint — same `splunk.singlevalue` tiles + `absolute` layout you'd put in an ITSI Glass Table, but using the actively-maintained native renderer. Covers the `<dashboard version="2"><definition><![CDATA[<JSON>]]></definition></dashboard>` XML wrapper, the form-encoded POST body with `name` + `eai:data`, the `defaults.dataSources['ds.search']` shape (NOT `defaults.dataSources['global']` like glass tables — this is a real, undocumented difference), embedding backdrop images as data URIs (`splunk-enterprise-kvstore://` is ITSI-glass-table-only and does not resolve in Dashboard Studio), the `itsi` app context required so the `get_full_itsi_summary_kpi(<kpi_id>)` macro resolves, the SHKPI-<service_id> KPI ID convention for Service Health Scores, and the explicit recommendation to use Dashboard Studio over ITSI Glass Tables whenever the customer doesn't strictly require GT-specific features (swap services, ITSI-only annotations). Use when a customer asks for a service-flow visualisation that needs to be code-driven, when an ITSI Glass Table renders as a black screen (always pivot to DS), when you want a dashboard that scales reliably across Splunk Cloud minor versions, or when batching dashboard creation across an environment.
disable-model-invocation: true
---

# Splunk Dashboard Studio (v2) Dashboards via REST

Build a Splunk Dashboard Studio v2 dashboard end-to-end from a Python script: encode the backdrop PNG as a data URI, compose the JSON definition, wrap it in the dashboard XML, POST to `data/ui/views`, verify by GET.

**This is the recommended approach for code-driven service-health visualisations** even in ITSI environments. ITSI Glass Tables are a fork of an older Dashboard Studio snapshot with undocumented strict-mode constraints (silent React black-screen failures on minor schema deviations). Only use Glass Tables if you specifically need GT features like swap services or ITSI-only annotations.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use

- Customer asks for a service-flow map, executive overview, or sequential-flow visualisation that ties multiple ITSI services together
- An ITSI Glass Table renders as a black screen → pivot to Dashboard Studio (this skill)
- You need a dashboard that round-trips reliably across Splunk Cloud point releases
- You want dashboard creation to be idempotent / replayable (CI/CD, multi-environment rollout)
- Layout needs to reflect an architecture diagram (arrows, columns by perimeter) — easier to draw the diagram in PIL/Photoshop/Figma than to compose it in the dashboard JSON

## Key endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/servicesNS/-/<app>/data/ui/views` | GET (with `?search=`) | List dashboards / search by content |
| `/servicesNS/-/<app>/data/ui/views/<name>` | GET | Read one dashboard's XML |
| `/servicesNS/nobody/<app>/data/ui/views` | POST | Create a dashboard (form-encoded `name` + `eai:data`) |
| `/servicesNS/nobody/<app>/data/ui/views/<name>` | POST | Update an existing dashboard (form-encoded `eai:data` only) |
| `/servicesNS/nobody/<app>/data/ui/views/<name>` | DELETE | Remove (idempotent re-creation) |

App context choice:
- `itsi` — required when SHS / ITSI summary macros are used (`get_full_itsi_summary_kpi`, `service_level_kpi_only`). Most common for service-health dashboards.
- `search` — fine for raw SPL with no ITSI macros
- Custom app — when shipping the dashboard as part of an app package

## Critical gotchas

### Gotcha 1: this is NOT an ITSI Glass Table

ITSI Glass Tables and Dashboard Studio look similar (same `splunk.singlevalue` viz, same `absolute` layout, same `> primary | seriesByName(...)` reactive syntax) but are different code paths with different REST endpoints, different defaults shapes, and different error handling. Do not copy a GT JSON definition wholesale — at minimum the `defaults` shape needs translation (see Gotcha 4).

| Aspect | ITSI Glass Table | Dashboard Studio v2 |
|---|---|---|
| REST endpoint | `/itoa_interface/glass_table` | `/data/ui/views` |
| POST body | form-encoded `data=<JSON>` | form-encoded `name=<x>` + `eai:data=<XML>` |
| Payload format | Raw JSON | XML wrapping JSON in `<![CDATA[...]]>` |
| Backdrop image | `splunk-enterprise-kvstore://<key>` | data URI (`data:image/png;base64,...`) |
| Defaults key | `dataSources.global` | `dataSources['ds.search']` |
| Top-level fields | `swap_service_ids`, `selected_swap_service_id`, `interactable`, `gt_version=beta` | None of these |
| Error mode on bad schema | Silent black screen | Visible HTTP 400 with message |
| Renderer stability | Forked + brittle | Actively maintained |

### Gotcha 2: the dashboard XML wrapper

Dashboards are stored as XML, not JSON. The JSON definition is wrapped inside a `<definition>` element with a CDATA section:

```xml
<dashboard version="2" theme="light">
  <label>My Dashboard</label>
  <description>Optional description</description>
  <definition><![CDATA[
{ "title": "...", "visualizations": {...}, "dataSources": {...}, "inputs": {...}, "defaults": {...}, "layout": {...} }
]]></definition>
</dashboard>
```

Key elements:
- `version="2"` — REQUIRED for Dashboard Studio. Without it, Splunk parses as the legacy SimpleXML format and your JSON is ignored.
- `theme="light"` or `"dark"` — visual theme. `light` is better for dashboards with white backdrops.
- `<label>` — what users see in the app menu. UTF-8 plain text, no entities needed.
- CDATA — guards against the `<` and `>` inside the JSON. Escape any literal `]]>` in the JSON with the trick `]]]]><![CDATA[>`.

### Gotcha 3: POST body shape — `name` + `eai:data`

The `data/ui/views` POST is form-encoded. The full XML goes into `eai:data` (with the literal colon):

```python
body = {
    'name': 'my_dashboard_name',  # filesystem-safe: lowercase + underscores
    'eai:data': xml_string,
}
data = urllib.parse.urlencode(body).encode()
# Content-Type: application/x-www-form-urlencoded
```

To update an existing dashboard, POST to `/data/ui/views/<name>` (singular) with `eai:data` only — `name` is implied by the URL.

### Gotcha 4: `defaults.dataSources['ds.search']`, NOT `defaults.dataSources['global']`

This is the trap when porting from ITSI Glass Tables. Glass tables use a `global` key:

```json
// ITSI Glass Table — WRONG shape for Dashboard Studio
"defaults": {
  "dataSources": {
    "global": {
      "options": {
        "queryParameters": {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"},
        "refreshType": "delay",
        "refresh": "$global_refresh_rate$"
      }
    }
  }
}
```

Dashboard Studio keys defaults by the data-source TYPE (e.g. `ds.search`, `ds.savedsearch`):

```json
// Dashboard Studio v2 — CORRECT shape
"defaults": {
  "dataSources": {
    "ds.search": {
      "options": {
        "queryParameters": {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"},
        "refresh": "$global_refresh_rate$",
        "refreshType": "delay"
      }
    }
  }
}
```

Verified against several v2 dashboards in this stack (`BNW-app-powerconnect/basis_health_checks`, `itsi/event_analytics_audit_studio`). If you use `global`, defaults are silently ignored and your per-tile data sources will need explicit `queryParameters`.

### Gotcha 5: backdrop image MUST be a data URI

`splunk-enterprise-kvstore://<key>` is an ITSI-only URI scheme handled by the glass-table React tree. Dashboard Studio doesn't resolve it — the image just doesn't load. Use a base64-encoded data URI:

```python
import base64
with open('/path/to/backdrop.png', 'rb') as f:
    png_bytes = f.read()
data_uri = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode()

layout['options']['backgroundImage'] = {
    'x': 0, 'y': 0,
    'src': data_uri,
    'sizeType': 'contain',  # 'cover' or 'contain' or 'auto'
}
```

Practical size limits: Splunk Cloud accepts dashboard XMLs up to a few MB without issue. A 2667×1500 PNG with ~150 KB raw / 200 KB base64 is fine. For larger images, optimise the PNG (palettize, quantize, drop the alpha channel) before encoding.

### Gotcha 6: viz / dataSource IDs alphabet

Dashboard Studio is more permissive than ITSI Glass Tables (it accepts underscores) but still rejects hyphens, periods, and spaces. Safe pattern: `[A-Za-z_][A-Za-z0-9_]*`. Recommended convention (matches the SAP-GT-Template and most existing v2 dashboards in this stack): `<prefix>_<10 alphanumeric chars>`.

```python
import random, string
_USED = set()
def short_id(prefix):
    while True:
        c = f'{prefix}_' + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        if c not in _USED:
            _USED.add(c); return c

vid = short_id('viz')   # e.g. 'viz_uhJBfCw7'
did = short_id('ds')    # e.g. 'ds_V7D0eBvv'
```

Never derive IDs from service / KPI names that may contain `-`, `.`, ` `, or `/`. Put labels in the viz `title` field or in the backdrop PNG.

### Gotcha 7: `get_full_itsi_summary_kpi` macro is in the SA-ITOA app

The macro is exported globally but only when the dashboard runs in an app that has access to it. The `itsi` app does; `search` does not by default. If you must host the dashboard in `search`, qualify the macro:

```spl
`SA-ITOA:get_full_itsi_summary_kpi(SHKPI-<svc_id>)`
```

Easiest path: just deploy to `itsi` (`/servicesNS/nobody/itsi/data/ui/views`).

### Gotcha 8: SHKPI ID convention

Every ITSI service has a Service Health Score KPI with the deterministic `_key`:

```
SHKPI-<service_key>
```

No need to GET the service first — just prepend `SHKPI-` to the service ID. `alert_color` is a hex string ITSI computes from the severity — feed it straight into `backgroundColor` of `splunk.singlevalue`.

```spl
`get_full_itsi_summary_kpi(SHKPI-8af048da-102b-4543-9874-5fc03e23be7f)` `service_level_kpi_only`
| timechart cont=false latest(alert_value) AS alert_value, latest(alert_color) AS alert_color
```

### Gotcha 9: dashboard `name` is the URL slug, not the label

The `name` you POST becomes the URL slug (`/app/<app>/<name>`) and the filename of the persisted XML. It must be lowercase alphanumeric with underscores — no spaces, no hyphens, no special chars. The user-facing title is the `<label>` inside the XML.

```python
NAME  = 'buttercup_service_flow_map_pov'    # URL slug: /app/itsi/buttercup_service_flow_map_pov
LABEL = 'Buttercup - Service Flow Map' # what users see in the menu
```

### Gotcha 10: dashboards are user-owned by default

POSTing to `/servicesNS/nobody/<app>/data/ui/views` creates the dashboard in the `nobody` namespace but ACL `owner` is stamped to the calling user. Sharing defaults to `app` (visible to all users in that app). To share globally, PATCH the ACL afterwards:

```python
req('POST', f'/servicesNS/{owner}/{app}/data/ui/views/{name}/acl',
    body={'sharing': 'global', 'owner': owner, 'perms.read': '*', 'perms.write': '*'})
```

## Reference implementation

A ready-to-copy version of this script lives next to this SKILL.md as
[`template_build_dashboard.py`](./template_build_dashboard.py). Copy it
to `<project>/_tools/build_dashboard.py`, edit the CONFIG block (URL,
app, name, label, BG_PNG path) + the `TILES` list + `SHS_MAP`, and run.

## Standard script template (inline)

```python
"""Build (or replace) a Dashboard Studio v2 dashboard programmatically."""
import base64, json, os, random, ssl, string, urllib.parse, urllib.request

URL = os.environ['ITSI_URL'].rstrip('/')  # https://<stack>.splunkcloud.com:8089
TOK = os.environ['ITSI_TOKEN']
CTX = ssl._create_unverified_context()  # adjust per policy

APP   = 'itsi'                          # so ITSI macros resolve
NAME  = 'my_dashboard'                  # URL slug + filename
LABEL = 'My Custom Service Flow Map'    # user-facing title
DESC  = 'Programmatic v0.1.'
BG_PNG = './backdrop.png'

SHS_MAP = {
    'Invoicing - Functional': {
        'service_id':  'ee7a0281-d9c0-4a11-a6fe-e382dc709e4e',
        'shs_kpi_id':  'SHKPI-ee7a0281-d9c0-4a11-a6fe-e382dc709e4e',
    },
    # ...
}

# ---- HTTP helper ----

def req(method, path, body=None, content_type=None):
    h = {'Authorization': f'Bearer {TOK}'}
    data = None
    if isinstance(body, dict):
        h['Content-Type'] = content_type or 'application/x-www-form-urlencoded'
        data = urllib.parse.urlencode(body, doseq=True).encode()
    elif isinstance(body, str):
        h['Content-Type'] = content_type or 'application/json'
        data = body.encode()
    path += ('&' if '?' in path else '?') + 'output_mode=json'
    r = urllib.request.Request(f'{URL}{path}', data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=60) as resp:
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode(errors='replace')

# ---- ID helper ----

_USED = set()
_ALPH = string.ascii_letters + string.digits
def short_id(prefix):
    while True:
        c = f'{prefix}_' + ''.join(random.choices(_ALPH, k=10))
        if c not in _USED:
            _USED.add(c); return c

# ---- Builders ----

def make_ds(name, service_id, shs_kpi_id):
    return {
        'name': f'{name} - SHS',
        'type': 'ds.search',
        'options': {
            'query': (f'`get_full_itsi_summary_kpi({shs_kpi_id})` `service_level_kpi_only` '
                      f'| timechart cont=false latest(alert_value) AS alert_value, '
                      f'latest(alert_color) AS alert_color'),
        },
        'meta': {'serviceID': service_id, 'kpiID': shs_kpi_id},
    }

def make_viz(ds_id, title):
    return {
        'type': 'splunk.singlevalue',
        'dataSources': {'primary': ds_id},
        'title': title,
        'options': {
            'sparklineStrokeColor': '#FFFFFF',
            'majorColor': '#FFFFFF',
            'backgroundColor': '> primary | seriesByName("alert_color") | lastPoint()',
            'sparklineValues': '> primary | seriesByName("alert_value")',
            'sparklineDisplay': 'off',
            'trendDisplay': 'off',
            'showSparklineTooltip': True,
        },
    }

def build_definition(bg_data_uri, tiles):
    """tiles: list of (service_name, x, y, w, h)."""
    vizs, dss, structure = {}, {}, []
    for (name, x, y, w, h) in tiles:
        m = SHS_MAP[name]
        vid, did = short_id('viz'), short_id('ds')
        dss[did]  = make_ds(name, m['service_id'], m['shs_kpi_id'])
        vizs[vid] = make_viz(did, name)
        structure.append({'type': 'block', 'item': vid,
                          'position': {'x': x, 'y': y, 'w': w, 'h': h}})

    return {
        'title': LABEL,
        'description': DESC,
        'visualizations': vizs,
        'dataSources': dss,
        'inputs': {
            'input_global_trp': {
                'type': 'input.timerange', 'title': 'Time Range',
                'options': {'defaultValue': '-60m, now', 'token': 'global_time'},
            },
            'input_global_refresh_rate': {
                'type': 'input.dropdown', 'title': 'Refresh',
                'options': {'defaultValue': '300s', 'token': 'global_refresh_rate',
                            'items': [{'value':'60s','label':'1m'},
                                      {'value':'300s','label':'5m'},
                                      {'value':'1800s','label':'30m'},
                                      {'value':'3600s','label':'1h'}]},
            },
        },
        'defaults': {
            # KEY: 'ds.search' not 'global' (see Gotcha 4)
            'dataSources': {
                'ds.search': {
                    'options': {
                        'queryParameters': {'earliest': '$global_time.earliest$',
                                            'latest':   '$global_time.latest$'},
                        'refresh':     '$global_refresh_rate$',
                        'refreshType': 'delay',
                    },
                },
            },
        },
        'layout': {
            'type': 'absolute',
            'globalInputs': ['input_global_trp', 'input_global_refresh_rate'],
            'structure': structure,
            'options': {
                'width': 2667, 'height': 1500,
                'display': 'auto-scale',
                'backgroundColor': '#FFFFFF',
                'backgroundImage': {
                    'x': 0, 'y': 0,
                    'src': bg_data_uri,           # data URI, not kvstore URL
                    'sizeType': 'contain',
                },
                'showTitleAndDescription': True,
            },
        },
    }

def build_xml(definition):
    s = json.dumps(definition).replace(']]>', ']]]]><![CDATA[>')
    return (f'<dashboard version="2" theme="light">\n'
            f'  <label>{LABEL}</label>\n'
            f'  <description>{DESC}</description>\n'
            f'  <definition><![CDATA[{s}]]></definition>\n'
            f'</dashboard>')

# ---- Deploy ----

TILES = [
    ('Invoicing - Functional', 232, 440, 280, 80),
    # ...
]

def main():
    with open(BG_PNG, 'rb') as f:
        data_uri = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
    xml = build_xml(build_definition(data_uri, TILES))

    # idempotent: delete existing if present
    req('DELETE', f'/servicesNS/nobody/{APP}/data/ui/views/{NAME}')
    # create
    s, resp = req('POST', f'/servicesNS/nobody/{APP}/data/ui/views',
                  body={'name': NAME, 'eai:data': xml})
    assert s == 201, f'create failed: {s} {resp}'
    print(f'created: https://<host>/en-GB/app/{APP}/{NAME}')

if __name__ == '__main__':
    main()
```

## Layout strategies

Same as ITSI Glass Tables — the layout primitives are identical (`absolute` positioning, `splunk.singlevalue` tiles, PNG backdrop). See the `splunk-itsi-glass-table-rest` skill's "Layout strategies" section for canvas dimensions, tile sizing, and the 4-column perimeter-lanes pattern.

The "background carries the story, tiles carry the data" pattern works exactly the same way here: put all static visual elements (logos, column headings, perimeter labels, sequential-flow arrows, legends) in the PNG backdrop, and overlay live `splunk.singlevalue` tiles at fixed pixel coordinates.

## Verifying after POST

```python
# 1. Round-trip the JSON cleanly
s, d = req('GET', f'/servicesNS/-/{APP}/data/ui/views/{NAME}')
import re
m = re.search(r'<definition>\s*<!\[CDATA\[(.+?)\]\]></definition>', d['entry'][0]['content']['eai:data'], re.S)
defn = json.loads(m.group(1))  # must parse cleanly

# 2. All structure -> viz refs resolve
bad = [s['item'] for s in defn['layout']['structure'] if s['item'] not in defn['visualizations']]
assert not bad, f'orphan structure items: {bad}'

# 3. All viz -> ds refs resolve
for vid, v in defn['visualizations'].items():
    for k, ref in v.get('dataSources', {}).items():
        assert ref in defn['dataSources'], f'{vid}.{k} -> {ref} not found'

# 4. Backdrop is a data URI
assert defn['layout']['options']['backgroundImage']['src'].startswith('data:'), \
    'backgroundImage must be a data URI (splunk-enterprise-kvstore:// only works in GTs)'

# 5. A sample data source actually returns rows
import urllib.parse
sample_q = next(iter(defn['dataSources'].values()))['options']['query']
form = urllib.parse.urlencode({'search': f'search {sample_q}',
                               'output_mode': 'json',
                               'earliest_time': '-60m', 'latest_time': 'now'}).encode()
# POST to /servicesNS/nobody/<APP>/search/jobs/oneshot ...
```

User-facing URL after a successful POST:

```
https://<stack>.splunkcloud.com/en-GB/app/<APP>/<NAME>
```

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Lifting a glass-table JSON definition wholesale into Dashboard Studio | `defaults.dataSources.global` is silently ignored; `swap_service_ids` etc are unknown fields | Translate `global` -> `ds.search`; strip glass-table-only top-level fields |
| Using `splunk-enterprise-kvstore://<key>` for the backdrop | Dashboard Studio doesn't resolve this scheme; image just doesn't appear | Encode as `data:image/png;base64,...` |
| Hyphens in viz/ds IDs (e.g. `viz_Invoicing-Functional`) | Renderer rejects; tiles don't appear | `[A-Za-z_][A-Za-z0-9_]*` only; use `short_id()` helper |
| Forgetting `version="2"` in the dashboard XML | Splunk parses as legacy SimpleXML; your JSON is silently ignored | Always set `<dashboard version="2" ...>` |
| Hosting an ITSI-macro dashboard in the `search` app | `get_full_itsi_summary_kpi` doesn't resolve; data sources fail with "macro not found" | Host in `itsi` app, OR qualify as `SA-ITOA:get_full_itsi_summary_kpi(...)` |
| Using `name='My Cool Dashboard'` | URL slug breaks (spaces, capitals); some browsers refuse the URL | `name` must be lowercase alphanumeric + underscores; put the friendly title in `<label>` |
| Editing the dashboard in the GUI after a script run, then re-running the script | UI changes are silently discarded by the next DELETE+POST | Treat the script as the source of truth; commit it to the project repo |
| Generating a corporate logo from scratch | Trademark / brand integrity issues; customer will reject | Download the real logo (Wikimedia Commons public-domain trademark files, or the customer's brand portal) |

## Related skills

- `splunk-itsi-glass-table-rest` — companion skill for ITSI Glass Tables. Prefer this skill (Dashboard Studio) unless you specifically need GT features.
- `splunk-itsi-api-access` — base ITSI REST patterns (auth, ssl, paging)
- `splunk-itsi-service-tree-design` — designing the service tree that the dashboard will visualise
- `splunk-itsi-kpi-creation-via-api` — companion pattern for creating KPIs the dashboard will surface
