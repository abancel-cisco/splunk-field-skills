#!/usr/bin/env python3
"""Splunk Dashboard Studio (v2) builder template — copy to <project>/_tools/
build_dashboard.py and edit the CONFIG block + the TILES list + SHS_MAP
for your project.

What this script does
=====================
Builds a Splunk Dashboard Studio v2 dashboard with N single-value tiles
(coloured by ITSI Service Health Score severity) overlaid on a static
backdrop PNG. The PNG is embedded in the dashboard as a base64 data URI
so the dashboard is self-contained — no KV-store dependency, no app-static
asset to ship separately.

Why Dashboard Studio (and not an ITSI Glass Table)
==================================================
ITSI Glass Tables fork from an older Dashboard Studio snapshot and the
React canvas silently black-screens on minor schema deviations (no error
visible to the user, no console fallback). Dashboard Studio v2 is the
actively-maintained native renderer in Splunk Cloud, returns proper HTTP
400s with messages when the schema is wrong, and uses the same primitives
(`splunk.singlevalue` viz, `absolute` layout, `> primary | seriesByName`
reactive syntax). Use a glass table ONLY if you specifically need GT
features (swap services, ITSI-only annotations).

Re-running the script is idempotent: it DELETEs any existing dashboard
with the same `name`, then POSTs the fresh version. The script is the
source of truth — GUI edits between runs are silently overwritten.

Prerequisites
=============
- Python 3.8+ (stdlib only, no third-party deps)
- A Splunk Enterprise / Cloud bearer token with capabilities:
    list_inputs, edit_view (for the target app), search
- A backdrop PNG sized to your chosen canvas (default 2667 x 1500)
- For ITSI SHS tiles: the dashboard must be hosted in the `itsi` app so
  the `get_full_itsi_summary_kpi` macro resolves (or qualify it as
  `SA-ITOA:get_full_itsi_summary_kpi(...)`)

Run
===
    export SPLUNK_URL='https://<stack>.splunkcloud.com:8089'
    export SPLUNK_TOKEN='<bearer-token>'
    python3 build_dashboard.py
"""

import base64
import json
import os
import random
import ssl
import string
import sys
import urllib.error
import urllib.parse
import urllib.request


# ============================================================================
# CONFIG — edit for your project
# ============================================================================

URL = os.environ['SPLUNK_URL'].rstrip('/')
TOK = os.environ['SPLUNK_TOKEN']
CTX = ssl._create_unverified_context()  # adjust per your security policy

APP   = 'itsi'                              # use 'itsi' for ITSI macros to resolve
NAME  = 'my_service_flow_map'               # URL slug; lowercase + underscores ONLY
LABEL = 'My Service Flow Map'               # user-facing title
DESC  = 'Programmatic v0.1 — built via Dashboard Studio REST.'
THEME = 'light'                             # 'light' or 'dark'

BG_PNG = '/path/to/backdrop.png'            # 2667 x 1500 recommended

# ITSI service -> {service_id, shs_kpi_id} map. shs_kpi_id is always
# `SHKPI-<service_id>` (deterministic; no need to GET the service).
SHS_MAP = {
    'My Service A': {
        'service_id': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        'shs_kpi_id': 'SHKPI-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    },
    # 'My Service B': {...},
}

# Tile placements. Each entry is (service_name, x, y, w, h) in canvas pixels.
# The backdrop PNG dimensions MUST match `layout.options.{width,height}` below
# or the tiles will drift relative to the backdrop.
BIG_W, BIG_H = 280, 80       # use for headline tiles (1 per perimeter)
SUB_W, SUB_H = 195, 55       # use for sub-component tiles
TILES = [
    ('My Service A',  232, 440, BIG_W, BIG_H),
    # ('My Service B', 742, 440, BIG_W, BIG_H),
]

CANVAS_W, CANVAS_H = 2667, 1500


# ============================================================================
# Implementation — usually doesn't need editing
# ============================================================================


def req(method, path, body=None, content_type=None):
    """Minimal Splunk REST helper. Form-encodes dict bodies, JSON-encodes str
    bodies. Always asks for JSON output. Returns (status, parsed_body)."""
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
        with urllib.request.urlopen(r, context=CTX, timeout=120) as resp:
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode(errors='replace')


# 10-char alphanumeric IDs — matches the convention used by existing v2
# dashboards in Splunk Cloud. Never derive IDs from service / KPI names that
# may contain '-', '.', ' ', or '/' — Dashboard Studio rejects those.
_USED_IDS = set()
_ID_ALPHABET = string.ascii_letters + string.digits

def short_id(prefix):
    while True:
        c = f'{prefix}_' + ''.join(random.choices(_ID_ALPHABET, k=10))
        if c not in _USED_IDS:
            _USED_IDS.add(c)
            return c


def make_ds(service_name, service_id, shs_kpi_id):
    """Search data source for one SHS KPI.

    NOTE: queryParameters (earliest/latest) are injected globally via
    `defaults.dataSources['ds.search']` — don't duplicate them here."""
    return {
        'name': f'{service_name} - SHS',
        'type': 'ds.search',
        'options': {
            'query': (
                f'`get_full_itsi_summary_kpi({shs_kpi_id})` `service_level_kpi_only` '
                f'| timechart cont=false latest(alert_value) AS alert_value, '
                f'latest(alert_color) AS alert_color'
            ),
        },
        'meta': {'serviceID': service_id, 'kpiID': shs_kpi_id},
    }


def make_viz(ds_id, service_name):
    """Single-value tile coloured by the SHS severity (`alert_color`).
    Keep the field set minimal — extra options confuse older renderers."""
    return {
        'type': 'splunk.singlevalue',
        'dataSources': {'primary': ds_id},
        'title': service_name,
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


def build_definition(bg_data_uri):
    vizs, dss, structure = {}, {}, []
    placed = []
    for (svc_name, x, y, w, h) in TILES:
        if svc_name not in SHS_MAP:
            print(f'  WARN: "{svc_name}" missing from SHS_MAP, skipping')
            continue
        m = SHS_MAP[svc_name]
        vid, did = short_id('viz'), short_id('ds')
        dss[did]  = make_ds(svc_name, m['service_id'], m['shs_kpi_id'])
        vizs[vid] = make_viz(did, svc_name)
        structure.append({
            'type': 'block',
            'item': vid,
            'position': {'x': x, 'y': y, 'w': w, 'h': h},
        })
        placed.append(svc_name)
    print(f'  placed {len(placed)} tiles')

    inputs = {
        'input_global_trp': {
            'type': 'input.timerange',
            'title': 'Time Range',
            'options': {'defaultValue': '-60m, now', 'token': 'global_time'},
        },
        'input_global_refresh_rate': {
            'type': 'input.dropdown',
            'title': 'Refresh',
            'options': {
                'defaultValue': '300s',
                'token': 'global_refresh_rate',
                'items': [
                    {'value': '60s',   'label': '1 Minute'},
                    {'value': '300s',  'label': '5 Minutes'},
                    {'value': '1800s', 'label': '30 Minutes'},
                    {'value': '3600s', 'label': '1 Hour'},
                ],
            },
        },
    }

    # Dashboard-Studio defaults are keyed by data-source TYPE (e.g. 'ds.search'),
    # NOT by 'global' as in ITSI Glass Tables. This is the trap when porting
    # a GT definition — wrong key here means time-range tokens are silently
    # ignored and every tile shows "All time".
    defaults = {
        'dataSources': {
            'ds.search': {
                'options': {
                    'queryParameters': {
                        'earliest': '$global_time.earliest$',
                        'latest':   '$global_time.latest$',
                    },
                    'refresh':     '$global_refresh_rate$',
                    'refreshType': 'delay',
                },
            },
        },
    }

    layout = {
        'type': 'absolute',
        'globalInputs': ['input_global_trp', 'input_global_refresh_rate'],
        'structure': structure,
        'options': {
            'width': CANVAS_W,
            'height': CANVAS_H,
            'display': 'auto-scale',
            'backgroundColor': '#FFFFFF',
            'backgroundImage': {
                # MUST be a data URI — splunk-enterprise-kvstore:// is
                # ITSI-glass-table-only and silently fails to load in
                # Dashboard Studio.
                'x': 0, 'y': 0,
                'src': bg_data_uri,
                'sizeType': 'contain',
            },
            'showTitleAndDescription': True,
        },
    }

    return {
        'title': LABEL,
        'description': DESC,
        'visualizations': vizs,
        'dataSources':    dss,
        'inputs':         inputs,
        'defaults':       defaults,
        'layout':         layout,
    }


def build_xml(definition):
    """Wrap the JSON definition in the dashboard-studio v2 XML.
    `version="2"` is REQUIRED — without it Splunk falls back to legacy
    SimpleXML parsing and your JSON is ignored."""
    s = json.dumps(definition)
    s = s.replace(']]>', ']]]]><![CDATA[>')  # guard against CDATA terminator
    return (
        f'<dashboard version="2" theme="{THEME}">\n'
        f'  <label>{LABEL}</label>\n'
        f'  <description>{DESC}</description>\n'
        f'  <definition><![CDATA[{s}]]></definition>\n'
        f'</dashboard>'
    )


def main():
    print('\n=== Step 1: encode backdrop PNG as data URI ===')
    with open(BG_PNG, 'rb') as f:
        png_bytes = f.read()
    bg_data_uri = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode()
    print(f'  png size:      {len(png_bytes):,} bytes')
    print(f'  data uri size: {len(bg_data_uri):,} chars')

    print('\n=== Step 2: build dashboard definition ===')
    defn = build_definition(bg_data_uri)
    print(f'  vizs:        {len(defn["visualizations"])}')
    print(f'  dataSources: {len(defn["dataSources"])}')
    print(f'  structure:   {len(defn["layout"]["structure"])}')

    print('\n=== Step 3: wrap in dashboard XML ===')
    xml = build_xml(defn)
    print(f'  xml size: {len(xml):,} chars')

    print('\n=== Step 4: delete existing dashboard (idempotent) ===')
    s, _ = req('DELETE', f'/servicesNS/nobody/{APP}/data/ui/views/{NAME}')
    print(f'  HTTP {s} (404 = was not there, fine)')

    print('\n=== Step 5: POST dashboard ===')
    s, resp = req('POST', f'/servicesNS/nobody/{APP}/data/ui/views',
                  body={'name': NAME, 'eai:data': xml})
    if s not in (200, 201):
        print(f'  FAILED: HTTP {s}')
        print(f'  body: {resp[:1500] if isinstance(resp, str) else resp}')
        sys.exit(1)
    print(f'  HTTP {s}')

    print('\n=== Step 6: verify by GET ===')
    s, vresp = req('GET', f'/servicesNS/-/{APP}/data/ui/views/{NAME}')
    if s == 200:
        e = vresp['entry'][0]
        print(f'  label:     {e["content"].get("label")!r}')
        print(f'  isVisible: {e["content"].get("isVisible")}')
        print(f'  sharing:   {e["acl"]["sharing"]}')
    else:
        print(f'  WARN: GET returned HTTP {s}')

    web_host = URL.replace(':8089', '').replace('https://', '')
    print('\n=== Done ===')
    print(f'  https://{web_host}/en-GB/app/{APP}/{NAME}')


if __name__ == '__main__':
    main()
