---
name: splunk-itsi-glass-table-rest
category: itsi
description: Create ITSI Glass Tables programmatically via REST API — Service-Health-Score tiles overlaid on a custom backdrop image. Covers the gt_version=beta schema (visualizations / dataSources / layout.structure / inputs / defaults), the form-encoded `data=<JSON>` body convention that ITSI's itoa_interface endpoint requires (raw JSON returns "owner fields corrupted or missing in payload"), the SA-ITOA_files KV store collection used for backdrop images (base64 in `data` field, referenced via `splunk-enterprise-kvstore://<_key>`), the `get_full_itsi_summary_kpi(<kpi_id>)` macro pattern, the SHKPI-<service_id> ID convention for Service Health Score KPIs, and the "background carries the story, tiles carry the data" composition pattern proven on the SAP-GT-Template and reused for Buttercup. Use when someone asks for a custom glass table that visualises service interactions / sequential flows / cross-perimeter dependencies, when you need to produce a glass table from a service tree without clicking through the GUI, when batching glass-table creation across an environment, or when you want a backdrop that combines a real organisation logo with directional flow arrows.
disable-model-invocation: true
---

# ITSI Glass Tables via REST

> **Prefer `splunk-dashboard-studio-rest` unless you specifically need glass-table features.** ITSI Glass Tables are a fork of an older Dashboard Studio snapshot with undocumented strict-mode constraints — schema deviations black-screen the React canvas silently (no console error visible, no fallback). Dashboard Studio v2 is the actively-maintained native renderer, has predictable HTTP 400 errors when the schema is wrong, and supports the same `splunk.singlevalue` + `absolute` layout primitives. Only use this skill when a glass table is explicitly required (e.g. for swap-services or ITSI-only annotations) or when ingesting an existing glass table.

Build an ITSI Glass Table (gt_version=beta) end-to-end from a Python script: generate the backdrop PNG, upload it to KV store, compose the JSON definition, POST it, verify by GET. The "background carries the story, tiles carry the data" pattern keeps the glass-table JSON small while still letting you express rich layouts (logos, perimeter columns, sequential flow arrows).

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use

- Someone asks for a "service flow map" / "executive overview" / "sequence-of-flows" visualisation that ties multiple ITSI services together
- The service tree is large (>10 services) and clicking through the GT designer for every tile is impractical
- The layout needs to reflect an architecture diagram (arrows, columns by perimeter, sequential flows) — easier to draw the diagram in PIL/Photoshop/Figma than to compose it in the GT designer
- You need glass-table creation to be idempotent / replayable (CI/CD, multi-environment rollout)
- You want a glass table that includes a real logo (download it; never generate corporate logos)

## Key endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/servicesNS/nobody/SA-ITOA/storage/collections/data/SA-ITOA_files` | GET (with `?query={"name":"..."}`) | Find an existing backdrop record by filename |
| `/servicesNS/nobody/SA-ITOA/storage/collections/data/SA-ITOA_files` | POST (JSON body) | Upload new backdrop (base64-encoded PNG/JPG in `data` field) |
| `/servicesNS/nobody/SA-ITOA/storage/collections/data/SA-ITOA_files/<_key>` | DELETE | Remove an old backdrop before re-uploading |
| `/servicesNS/nobody/SA-ITOA/itoa_interface/glass_table` | GET | List glass tables |
| `/servicesNS/nobody/SA-ITOA/itoa_interface/glass_table` | POST | Create a glass table (form-encoded `data=<JSON>`) |
| `/servicesNS/nobody/SA-ITOA/itoa_interface/glass_table/<_key>` | DELETE | Replace by delete + create (idempotent re-runs) |
| `/servicesNS/nobody/SA-ITOA/itoa_interface/service/<_key>` | GET | Resolve a service's KPI list to find the ServiceHealthScore KPI ID |

## Critical gotchas

### Gotcha 1: form-encoded body, not JSON body

The `itoa_interface/glass_table` POST endpoint refuses raw `application/json` with:

```
HTTP 400: {"message":"owner fields corrupted or missing in payload. kwargs: {'data': {'title': ...}}"}
```

The kwargs preview gives the trick away: the API expects the payload as a form-encoded single `data` key whose value is the JSON string.

```python
# WRONG — returns "owner fields corrupted or missing"
req('POST', '/.../itoa_interface/glass_table', body=json.dumps(payload),
    headers_extra={'Content-Type':'application/json'})

# RIGHT — form-encoded, ITSI parses `data` as the payload JSON
req('POST', '/.../itoa_interface/glass_table',
    body={'data': json.dumps(payload)})  # urlencode handles it
```

The same applies to other `itoa_interface/*` POST endpoints (services, KPI base searches, threshold templates).

### Gotcha 2: SHKPI ID convention

Every ITSI service has a Service Health Score KPI with the deterministic `_key`:

```
SHKPI-<service_key>
```

Use this directly in your tile data source — no need to GET the service first unless you also want non-SHS KPIs. The `get_full_itsi_summary_kpi(<kpi_id>)` macro accepts the SHKPI ID:

```spl
`get_full_itsi_summary_kpi(SHKPI-8af048da-102b-4543-9874-5fc03e23be7f)` `service_level_kpi_only`
| timechart cont=false latest(alert_value) AS alert_value, latest(alert_color) AS alert_color
```

`alert_color` is a hex string ITSI computes from the severity — feed it straight into `backgroundColor` of `splunk.singlevalue`.

### Gotcha 3: backdrop image must live in SA-ITOA_files (NOT itsi_image_collection)

The KV store collection name is `SA-ITOA_files` (note the hyphen and case). Common wrong guesses that all return 404:

```
itsi_image_collection
itoa_image_collection
sa_itoa_image_collection
drawing_image_collection
```

Record schema:

```json
{
  "_key": "<24-hex-chars>",            // assigned by KV store on POST
  "name": "my-backdrop.png",
  "type": "image/png",
  "data": "<base64 of the PNG bytes>",
  "created_on": <unix_ts_float>,
  "created_by": "<user-or-tag>",
  "metadata": {"version": "V1"}
}
```

After upload, reference the image from the glass-table layout via:

```json
"layout": {
  "options": {
    "backgroundImage": {
      "x": 0, "y": 0,
      "src": "splunk-enterprise-kvstore://<that_key>",
      "sizeType": "contain"
    }
  }
}
```

### Gotcha 4: `gt_version: "beta"` is REQUIRED for the modern schema

Without `"gt_version":"beta"`, ITSI defaults to the legacy SVG-coords schema (`svg_content` + `svg_coords` fields), which is incompatible with the `definition.{visualizations,dataSources,layout}` shape used here. Always set it explicitly:

```json
{
  "title": "...",
  "identifying_name": "kebab-case-id",
  "gt_version": "beta",
  "interactable": true,
  "object_type": "glass_table",
  "definition": { ... }
}
```

`identifying_name` becomes the stable handle for idempotent updates — query with `?query={"identifying_name":"..."}` to find and DELETE before re-POSTing. Note: ITSI lowercases the `identifying_name` value server-side; check using lowercase when querying.

## The "background carries the story" pattern

The SAP-GT-Template that ships with ITSI uses **54 single-value tiles** and **zero text labels / arrows / shapes**. All static visual elements — column headings, perimeter labels, sequential-flow arrows, legends, logos — live in the PNG backdrop. Live tiles overlay the backdrop at fixed (x, y) pixel coordinates.

Why this works:
- The beta schema's only practical viz type is `splunk.singlevalue` (others exist but are niche)
- Drawing arrows / shapes in JSON would mean reverse-engineering the React component schema, which moves between minor versions
- A pre-rendered PNG is timeless and trivially editable in any image tool

Implementation:
1. Pick canvas dimensions (the SAP template uses `2667 × 1500`; that scales nicely on most monitors and gives generous tile real estate)
2. Generate the backdrop PNG with PIL: white background, logo, title, perimeter column bands, flow arrows with Unicode/ASCII labels (avoid Unicode if your font might not support all glyphs — see Gotcha 6), layer dividers, footer text
3. Decide tile coordinates in the SAME coordinate space as the PNG. The simplest mental model: imagine the PNG as your design surface, then "drop" tiles at the spots where you left blank rectangles
4. Tile dimensions ~ `280×80` for the main row, `195×55` for sub-tiles works well at 2667-wide

### Gotcha 5: cross-perimeter flow arrows are best done as labels under the arrows in the PNG, not as separate viz items. Live data flowing through the arrow can't be represented in the beta schema (there's no animated arc primitive); use a small SHS tile next to the arrow if you need a live signal there.

### Gotcha 6: Unicode arrows can render as `□` boxes depending on the font

The default PIL font and many system fonts don't carry the `↔ ↑ ↓ →` glyphs. Either:
- Force a font you know has them (Apple Color Emoji, DejaVu Sans, Noto Sans Symbols 2), OR
- Use ASCII alternatives: `->`, `<-`, `<->`, `^`, `v`. Often clearer at small sizes anyway

### Gotcha 7: viz / dataSource IDs MUST be `[A-Za-z0-9_]+` only — dashes black-screen the renderer

The React canvas for `gt_version=beta` looks up viz and dataSource references using a strict identifier regex. If a viz ID contains a hyphen, a period, a space, or any other non-alphanumeric (`viz_001_Invoicing_-_Functional`, `viz.health-score`, `ds.ERP-DB`), the renderer **does not throw a visible error** — the whole canvas mounts as a black `<div>` with no tiles, no backdrop, no message. The GT is readable via REST, the JSON is valid, but the page just goes black.

The SAP-GT-Template convention is `viz_[A-Za-z0-9]{10}` and `ds_[A-Za-z0-9]{10}`. Mirror it:

```python
import random, string
_USED = set()
def short_id(prefix):
    """10-char [A-Za-z0-9] suffix — matches SAP-GT-Template convention."""
    while True:
        c = f'{prefix}_' + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        if c not in _USED:
            _USED.add(c); return c

vid = short_id('viz')   # e.g. 'viz_uhJBfCw7'
did = short_id('ds')    # e.g. 'ds_V7D0eBvv'
```

Never derive IDs from service/KPI names that may contain `-`, `.`, ` `, or `/`. Keep a separate map (`viz_id -> service_name`) for your own debugging and put any human-readable labels into the backdrop PNG or the viz `title` field — NOT the ID.

### Gotcha 8: missing `swap_service_ids` / `selected_swap_service_id` also triggers the black screen

ITSI's glass-table swap-service input is a top-level feature that the React canvas initialises BEFORE rendering any tile. If these two fields are absent from the GT object (not the `definition` — the top-level GT record itself), the swap-service initialiser throws and the canvas mounts as a black `<div>`. The same silent failure mode as Gotcha 7.

Always include both, even when you don't use the swap feature:

```python
payload = {
    'title': GT_TITLE, 'description': GT_DESC,
    'identifying_name': GT_IDNAME, 'gt_version': 'beta',
    'interactable': True, 'object_type': 'glass_table',
    '_owner': 'nobody', '_user': 'nobody',
    'mod_source': 'unknown',
    'swap_service_ids': [],                 # MANDATORY (empty list is fine)
    'selected_swap_service_id': None,       # MANDATORY (None is fine)
    'definition': definition,
}
```

### Gotcha 9: don't set `acl.owner` to a user different from the calling token

If you include an `acl` block with `acl.owner='admin'` but your bearer token belongs to a different user, the POST returns `HTTP 403: "Payload has inconsistent ownership, please verify owners <caller> and admin"`. Two safe options:

- Omit the `acl` block entirely — ITSI auto-populates it from the calling user (sharing defaults to `app`)
- Or set `acl.owner` to match the token's user (introspect via `/services/authentication/current-context`)

### Gotcha 10: black-screen triage checklist (when the GT page renders as a black canvas)

When a glass table renders as a black screen, work this list in order — the first match is almost always the cause:

1. Open browser DevTools console; React canvas errors are silent on screen but logged. Look for `Cannot read properties of undefined` referencing a viz or dataSource ID.
2. Verify every viz ID matches `^viz_[A-Za-z0-9_]+$` (Gotcha 7).
3. Verify every dataSource ID matches `^ds_[A-Za-z0-9_]+$` (Gotcha 7).
4. Verify every `structure[].item` resolves to a key in `definition.visualizations`.
5. Verify every `visualizations[].dataSources.primary` resolves to a key in `definition.dataSources`.
6. Verify top-level `swap_service_ids` (list) and `selected_swap_service_id` (null or string) are present (Gotcha 8).
7. Verify `gt_version == 'beta'` exactly (string).
8. Verify the backdrop `_key` in `definition.layout.options.backgroundImage.src` actually exists in the `SA-ITOA_files` KV store with a non-empty `data` field (NOT `payload`; the field name is `data`).
9. Compare top-level field set against `SAP-GT-Template` (`_key=ff8fb461-bba4-11ea-b52e-000d3a79206f`) — any key that template has and yours does not may be required.

The fastest diagnostic is a structural diff against SAP-GT-Template. Build a one-liner that GETs both and prints field-set deltas before opening the browser.

## Standard script template

```python
"""Build (or replace) a custom ITSI Glass Table programmatically.

Steps:
 1. Upload the backdrop PNG to SA-ITOA_files (idempotent: delete-by-name first).
 2. Compose the glass table JSON.
 3. POST (form-encoded `data=<JSON>`) to /itoa_interface/glass_table.
 4. Verify by GET.
"""
import base64, json, os, ssl, time, urllib.parse, urllib.request

URL = os.environ['ITSI_URL'].rstrip('/')
TOK = os.environ['ITSI_TOKEN']
CTX = ssl._create_unverified_context()  # adjust per policy

GT_IDNAME = 'my-glass-table'
GT_TITLE  = 'My Custom Service Flow Map'
BG_PNG    = './backdrop.png'
BG_NAME   = 'my-backdrop-v1.png'

# Service -> SHS KPI ID map (use SHKPI-<service_id> convention).
SHS_MAP = {
    'Invoicing - Functional': 'SHKPI-ee7a0281-d9c0-4a11-a6fe-e382dc709e4e',
    # ...
}


def req(method, path, body=None, extra_headers=None, raw=False):
    h = {'Authorization': f'Bearer {TOK}'}
    if extra_headers: h.update(extra_headers)
    data = None
    if isinstance(body, dict):
        data = urllib.parse.urlencode(body).encode()
        h.setdefault('Content-Type', 'application/x-www-form-urlencoded')
    elif isinstance(body, (bytes, bytearray)):
        data = body
    elif isinstance(body, str):
        data = body.encode()
        h.setdefault('Content-Type', 'application/json')
    r = urllib.request.Request(f'{URL}{path}', method=method, data=data, headers=h)
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=60) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload) if payload else None)
    except urllib.error.HTTPError as he:
        body_txt = he.read().decode(errors='replace')[:500]
        raise RuntimeError(f'HTTP {he.code} {method} {path}: {body_txt}')


def upload_backdrop():
    """Idempotent upload: delete existing by name, then POST a fresh record."""
    qs = urllib.parse.urlencode({'query': json.dumps({'name': BG_NAME}),
                                 'output_mode': 'json'})
    _, existing = req('GET',
                      f'/servicesNS/nobody/SA-ITOA/storage/collections/data/SA-ITOA_files?{qs}')
    if isinstance(existing, list) and existing:
        req('DELETE',
            f'/servicesNS/nobody/SA-ITOA/storage/collections/data/SA-ITOA_files/{existing[0]["_key"]}')

    with open(BG_PNG, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    record = {
        'name': BG_NAME, 'type': 'image/png', 'data': b64,
        'created_on': time.time(), 'created_by': 'gt-generator',
        'metadata': {'version': 'V1'},
    }
    _, resp = req('POST',
                  '/servicesNS/nobody/SA-ITOA/storage/collections/data/SA-ITOA_files',
                  body=json.dumps(record),
                  extra_headers={'Content-Type': 'application/json'})
    return resp['_key']


def delete_existing_glasstable():
    qs = urllib.parse.urlencode({'output_mode':'json','count':200,
                                 'fields':'_key,identifying_name,title'})
    _, gts = req('GET',
                 f'/servicesNS/nobody/SA-ITOA/itoa_interface/glass_table?{qs}')
    for g in gts if isinstance(gts, list) else []:
        # ITSI lowercases identifying_name server-side
        if g.get('identifying_name','').lower() == GT_IDNAME.lower() or g.get('title') == GT_TITLE:
            req('DELETE',
                f'/servicesNS/nobody/SA-ITOA/itoa_interface/glass_table/{g["_key"]}')


import random, string
_USED_IDS = set()
def short_id(prefix):
    """10-char [A-Za-z0-9] suffix — MUST match SAP-GT-Template convention or
    the React canvas black-screens (see Gotcha 7)."""
    while True:
        c = f'{prefix}_' + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        if c not in _USED_IDS:
            _USED_IDS.add(c); return c


def make_ds(name, service_id, shs_kpi_id):
    """Note: queryParameters are injected by defaults.dataSources.global —
    don't duplicate them here (matches SAP-GT-Template shape)."""
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


def make_viz(ds_id):
    """Field set mirrors SAP-GT-Template exactly. Extra fields (`title`,
    `unit`, `majorColor` vs `color`) are silently dropped by some ITSI
    versions and reject-render in others — keep this minimal."""
    return {
        'type': 'splunk.singlevalue',
        'dataSources': {'primary': ds_id},
        'options': {
            'sparklineStrokeColor': '#ffffff',
            'color': '#FFFFFF',
            'showSparklineTooltip': True,
            'backgroundColor': '> primary | seriesByName("alert_color") | lastPoint()',
            'sparklineValues': '> primary | seriesByName("alert_value")',
            'sparklineDisplay': 'off',
            'trendDisplay': 'off',
        },
        'context': {},
    }


def build_definition(bg_key, tiles):
    """tiles: list of (service_name, x, y, w, h)."""
    vizs, dss, structure = {}, {}, []
    for (name, x, y, w, h) in tiles:
        kpi_id = SHS_MAP[name]
        # Derive svc id from SHKPI- prefix
        svc_id = kpi_id[len('SHKPI-'):]
        vid = short_id('viz')   # NEVER derive from name (Gotcha 7)
        did = short_id('ds')
        dss[did]  = make_ds(name, svc_id, kpi_id)
        vizs[vid] = make_viz(did)
        structure.append({'type': 'block', 'item': vid,
                          'position': {'x': x, 'y': y, 'w': w, 'h': h}})
    return {
        'title': GT_TITLE, 'description': '',
        'visualizations': vizs, 'dataSources': dss,
        'inputs': {
            'input_global_trp': {
                'type': 'input.timerange', 'title': 'Time Range',
                'options': {'defaultValue': '-60m, now', 'token': 'global_time'}},
            'input_global_refresh_rate': {
                'type': 'input.dropdown', 'title': 'Refresh',
                'options': {'defaultValue': '300s', 'token': 'global_refresh_rate',
                            'items': [{'value':'60s','label':'1m'},
                                      {'value':'300s','label':'5m'},
                                      {'value':'1800s','label':'30m'},
                                      {'value':'3600s','label':'1h'}]}},
        },
        'defaults': {'dataSources': {'global': {'options': {
            'queryParameters': {'earliest': '$global_time.earliest$',
                                'latest':   '$global_time.latest$'},
            'refreshType': 'delay', 'refresh': '$global_refresh_rate$'}}}},
        'layout': {
            'type': 'absolute',
            'globalInputs': ['input_global_trp', 'input_global_refresh_rate'],
            'structure': structure,
            'options': {
                'width': 2667, 'height': 1500, 'backgroundColor': '#FFFFFF',
                'backgroundImage': {'x': 0, 'y': 0,
                                    'src': f'splunk-enterprise-kvstore://{bg_key}',
                                    'sizeType': 'contain'},
                'showTitleAndDescription': True,
            },
        },
    }


def create_glasstable(definition):
    # Mirror SAP-GT-Template top-level shape EXACTLY. Missing fields here
    # (especially swap_service_ids / selected_swap_service_id) silently
    # black-screen the canvas (see Gotcha 8).
    payload = {
        'title': GT_TITLE, 'description': '',
        'identifying_name': GT_IDNAME,
        'gt_version': 'beta', 'interactable': True,
        'object_type': 'glass_table',
        'mod_source': 'unknown',
        '_owner': 'nobody', '_user': 'nobody',
        'swap_service_ids': [],
        'selected_swap_service_id': None,
        # Don't set acl here — let ITSI auto-populate (see Gotcha 9).
        'definition': definition,
    }
    # CRITICAL: form-encoded body with a `data` key holding the JSON.
    _, resp = req('POST',
                  '/servicesNS/nobody/SA-ITOA/itoa_interface/glass_table',
                  body={'data': json.dumps(payload)})
    return resp


# Example tiles list (use coordinates that align with your backdrop):
TILES = [
    ('Invoicing - Functional', 232, 440, 280, 80),
    # ...
]

def main():
    bg_key = upload_backdrop()
    delete_existing_glasstable()
    defn = build_definition(bg_key, TILES)
    resp = create_glasstable(defn)
    print(f'created: {resp.get("_key")}')

if __name__ == '__main__':
    main()
```

## Layout strategies

### 4-column "perimeter lanes" (typical for a four-perimeter deployment)

- Canvas 2667 × 1500
- 4 columns at left-edges `[60, 742, 1424, 2106]`, width 622, gutter 60
- 3 horizontal layers: Functional (y=440), Platform (y=710), Components (y=980)
- Bottom band (y=1200+) for cross-cutting tiles (E2E business transactions, OTel pipeline health, etc.)
- Big tile: 280 × 80 (one per perimeter per layer)
- Sub-tile: 195 × 55 (three per perimeter in the Components layer)

### Single-perimeter deep dive

- Canvas 2000 × 1500
- 1 column, layered from raw infrastructure up to functional outcomes
- Tile size 380 × 100 for headline, 200 × 60 for components

### Executive overview ("traffic lights")

- Canvas 1200 × 800 (fits a laptop screen without scrolling)
- 2 rows × N columns of large 240 × 110 tiles
- Sparklines ON (`sparklineDisplay: 'auto'`) — gives 30-day trend at a glance

## Verifying after POST

Always GET the created glass table back and inspect:

- `gt_version` should be `'beta'` (legacy is `null` / absent)
- `definition.visualizations` count matches what you POSTed
- `definition.layout.options.backgroundImage.src` starts with `splunk-enterprise-kvstore://`
- Open the URL `https://<web-host>/en-GB/app/itsi/homeview?savedURLState=GlassTable&itsi.glass.table_id=<key>` and confirm tiles render coloured (data is flowing)
- If tiles show grey "No results": check that `service_level_kpi_only` macro is defined for your role and the KPI is actually emitting data into `itsi_summary`
- For Splunk Cloud: the web URL uses port 443 (no port suffix), management/REST URL uses port 8089 — keep them separate

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Sending raw `application/json` body to `/itoa_interface/glass_table` | Returns "owner fields corrupted or missing in payload" — wastes minutes debugging | Use form-encoded `{'data': json.dumps(payload)}` |
| Hardcoding the backdrop image path / KV `_key` | Re-runs end up referencing stale KV records | Upload-by-name (delete existing first, POST new, capture returned `_key`) |
| Forgetting `gt_version: "beta"` | Server falls back to legacy SVG-coords schema; your modern `definition` is ignored | Always include `"gt_version": "beta"` |
| Composing per-tile labels as separate viz items | Bloats JSON; misaligns with the SAP template approach; harder to maintain | Put all labels in the backdrop PNG; tiles are data-only |
| Animated / connector primitives | Don't exist in the beta schema; reverse-engineering newer React components is fragile across ITSI versions | Use PNG arrows + a small SHS tile next to the flow if you need a live signal there |
| Generating a corporate logo from scratch | Trademark / brand integrity issues; the brand owner will reject it | Download the real logo (Wikimedia Commons public-domain trademark files, or the organisation's brand portal) |
| Computing `SHKPI-<svc_id>` IDs by GETting the service first | Wastes API calls; the convention is deterministic | Just prepend `SHKPI-`; the service must exist (which you already know) |
| Using PNG dimensions that don't match the layout `width/height` | Tiles drift relative to the backdrop because ITSI scales the backdrop independently | Generate the PNG at the EXACT canvas dimensions declared in `layout.options.{width,height}` |
| Editing the glass table via UI after a script run, then re-running the script | UI changes are silently discarded by the next DELETE+POST | Treat the script as the source of truth; commit it to the project repo |

## Related skills

- `splunk-itsi-api-access` — base ITSI REST patterns (auth, ssl, paging)
- `splunk-itsi-service-tree-design` — designing the service tree that will be visualised
- `splunk-itsi-kpi-creation-via-api` — companion pattern for KPIs (also uses the form-encoded `data=<JSON>` convention)
- `splunk-itsi-content-pack-creation` — broader template for shipping ITSI artefacts as a package
