---
name: splunk-itsi-kpi-creation-via-api
category: itsi
description: Create and modify Splunk ITSI KPIs via the REST API at scale — clone a working KPI structure to N services, switch metrics within a shared base search, set entity binding fields, and avoid the silent-failure modes that make REST PATCH look broken when it's actually rolling back due to validation failures elsewhere in the payload. Covers KPI payload shapes for shared-base-search KPIs, default aggregate/entity thresholds required for Service Analyzer health scores (empty kpi_threshold_template_id alone yields alert_level=-1 / health_score=N/A), the read-modify-write pattern for the nested `kpis` array on a service, why clearing the `search` field on a shared-base KPI triggers silent rollback (and how that masquerades as `is_service_entity_filter` "not persisting"), idempotent bulk-replication scripts that skip already-existing titles, service-template locking when PATCHing KPI attrs, dispatching indicators with trigger_actions=1, the GUI-vs-REST mapping for KPI fields, units that get silently blanked, and the per-KPI fields that look optional but break health propagation when omitted. Use when implementing 6-8 KPIs across multiple services from a single base search, when KPI values populate but service/entity health scores stay gray or N/A, when an ITSI KPI is not behaving after a REST PATCH, when cloning a canary KPI to other leaves, when the user mentions kpi_base_search, base_search_metric, is_service_entity_filter, threshold_field, aggregate_thresholds, or asks about scripting ITSI KPI rollout instead of clicking through the UI.
disable-model-invocation: true
---

# ITSI KPI Creation via REST API

How to create, clone, and modify ITSI KPIs at scale via the REST API — and how to avoid the silent-failure modes that make `is_service_entity_filter` look unsettable when it's actually fine.

## When to use this skill

- You need to add the same KPI set to N services (e.g., 6 OS Hosts KPIs across 9 Platform leaves = 54 KPIs)
- A REST PATCH on a KPI returns 200 OK but the field doesn't change
- Cloning a working "canary" KPI to other services
- Bulk-modifying KPIs (e.g., switching all KPIs to a new base search after fork)
- KPI **values** show in Service Analyzer but **health scores stay gray / N/A**
- The user mentions `kpi_base_search`, `base_search_metric`, `is_service_entity_filter`, `threshold_field`, `aggregate_thresholds`
- You want to avoid the 50+ UI clicks the equivalent manual setup would take

Prerequisite: REST access already working (see `splunk-itsi-api-access`). Familiarity with the binding architecture (see `splunk-itsi-entity-binding-architecture`).

## KPI is not a top-level object — it's an array on the service

Unlike services, entities, or base searches, KPIs do NOT have their own `/itoa_interface/kpi` endpoint. They live as elements of the `kpis` array inside a service. So all KPI operations go through `/itoa_interface/service/<svc_key>` with the `kpis` array as the payload.

This means:
- Create a KPI = PATCH the service with the new kpis array
- Update a KPI = PATCH the service with the modified kpis array
- Delete a KPI = PATCH the service with the kpis array sans that element
- All operations use `?is_partial_data=1` to avoid clobbering other service fields

The ServiceHealthScore "KPI" (`_key` starts with `SHKPI-`) is auto-created by ITSI and should never be deleted or modified. Filter it out of clone operations but always include it in the PATCH payload.

## Anatomy of a shared-base-search KPI

The shared-base-search pattern is the right default: one base search per data source + entity type, many KPIs reference it. Compared to ad-hoc-search KPIs, shared-base KPIs:
- Run the base search ONCE per scheduling interval (one mstats, not N)
- Share entity binding configuration (one place to fix)
- Render faster in Service Analyzer

```json
{
  "_key": "<uuid>",
  "title": "CPU Utilization",
  "description": "Average CPU utilization across service-bound hosts",
  "search_type": "shared_base",
  "base_search_id":                "<base_search _key>",
  "base_search_metric":            "m_cpu",
  
  "is_entity_breakdown":           true,
  "entity_breakdown_id_fields":    "ITSIUniqueId",
  "entity_id_fields":              "ITSIUniqueId",
  "is_service_entity_filter":      true,
  
  "threshold_field":               "sa_cpu_utilization",
  "aggregate_thresholds": {
    "baseSeverityColor": "#5fbf7fff",
    "baseSeverityColorLight": "#5fbf7f33",
    "baseSeverityLabel": "normal",
    "baseSeverityValue": 2,
    "gaugeMax": 100,
    "gaugeMin": 0,
    "isMaxStatic": false,
    "isMinStatic": true,
    "metricField": "sa_cpu_utilization",
    "renderBoundaryMax": 100,
    "renderBoundaryMin": 0,
    "thresholdLevels": []
  },
  "entity_thresholds": { "...same shape as aggregate_thresholds, metricField matches threshold_field..." },
  "unit":                          "%",
  "fill_gaps":                     "null_value",
  "gap_severity":                  "info",
  "gap_severity_value":            "1",
  "gap_severity_color":            "#AED3E5",
  "gap_severity_color_light":      "#E3F0F6",
  
  "kpi_threshold_template_id":     "",
  "anomaly_detection_alerting_enabled": false,
  "enabled":                       1
}
```

Field-by-field:

| Field | Required? | Notes |
|---|---|---|
| `_key` | Yes | UUID. Generate locally (e.g., `str(uuid.uuid4())`). Do NOT reuse keys across services |
| `title` | Yes | Display name. Must be unique within the service's kpis array |
| `search_type` | Yes | `"shared_base"` for base-search-driven, `"adhoc"` for inline SPL (rare). Default to shared_base |
| `base_search_id` | Yes (if shared_base) | The `_key` of a `kpi_base_search` object |
| `base_search_metric` | Yes (if shared_base) | The `_key` of one of the base search's metrics. NOT the metric name |
| `is_entity_breakdown` | Yes | `true` to split by entity, `false` to show only aggregate |
| `entity_breakdown_id_fields` | Yes (if breakdown) | The alias used to split. Must exist as column in base search output |
| `entity_id_fields` | Yes (if breakdown) | The alias used to join back to entities. Usually same as breakdown |
| `is_service_entity_filter` | Yes (when scoping) | `true` to inject the entity-list WHERE clause. `false` shows all hosts in the data |
| `threshold_field` | Yes | The column in base search output whose value the KPI reports. Matches `metric.threshold_field` on the base search metric |
| `aggregate_thresholds` | **Yes for health scores** | Inline threshold spec for service-aggregate severity. Without this (and without `kpi_threshold_template_id`), present data maps to `alert_severity=unknown` / `alert_level=-1` |
| `entity_thresholds` | **Yes for health scores** | Same shape as `aggregate_thresholds` for per-entity severity. Usually identical to aggregate at deploy time |
| `unit` | No | Display unit. Constrained to a controlled list (see "blanked units" below) |
| `fill_gaps` | No | `null_value` (show null), `last_available_value`, `custom_value`. Default null_value |
| `gap_severity` / `gap_severity_value` / colors | No | Visual treatment when data is missing |
| `kpi_threshold_template_id` | No | Reference to a saved threshold template. Empty string is fine **if** inline `aggregate_thresholds` / `entity_thresholds` are set. Empty template + empty inline thresholds = no health score |
| `anomaly_detection_alerting_enabled` | No | Default false |
| `enabled` | No | Default 1 |

## Default thresholds — required for health scores

**Easy to overlook:** KPI data can flow (`alert_value` populated in `itsi_summary`) while Service Analyzer health scores stay **gray / N/A**. Root cause is almost always missing severity mapping on the KPI.

### Symptom chain (validated on ITSI 5.0, lab instance, 2026-07)

1. Indicator search runs; `itsi_summary` events have real `alert_value` (e.g. `backends=6`, `bch=100`)
2. Every event has `alert_severity=unknown` and `alert_level=-1`
3. `service_health_monitor` writes `health_score=N/A` for the service SHKPI and rollup parent
4. Service Analyzer shows no green/red health tile even though KPI sparklines have data

Working services (e.g. F5 BigIP from a shipped content pack) have `alert_level=2` (`normal`) and `health_score=100.0`.

### Why `kpi_threshold_template_id: ""` is not enough

An empty template ID means "no saved template" — it does **not** assign a default severity. ITSI needs either:

- A **`kpi_threshold_template_id`** pointing at a saved template, **or**
- Inline **`aggregate_thresholds`** + **`entity_thresholds`** on each KPI

Ship custom content packs with inline defaults at deploy time. Tune thresholds later (or swap in a template) once you know the metric distribution.

### Baseline "all-present-data-is-normal" pattern

Use when first bringing a content pack live. Maps any non-gap value to `normal` (`baseSeverityValue: 2`). Empty `thresholdLevels` = no warning/critical bands yet.

```python
def default_thresholds(metric_field: str) -> dict:
    return {
        "baseSeverityColor": "#5fbf7fff",
        "baseSeverityColorLight": "#5fbf7f33",
        "baseSeverityLabel": "normal",
        "baseSeverityValue": 2,
        "gaugeMax": 100,
        "gaugeMin": 0,
        "isMaxStatic": False,
        "isMinStatic": True,
        "metricField": metric_field,          # MUST match threshold_field
        "renderBoundaryMax": 100,
        "renderBoundaryMin": 0,
        "thresholdLevels": [],
    }

new_kpi = {
    # ... other KPI fields ...
    "threshold_field": "sa_cpu_utilization",
    "aggregate_thresholds": default_thresholds("sa_cpu_utilization"),
    "entity_thresholds":    default_thresholds("sa_cpu_utilization"),
    "kpi_threshold_template_id": "",
}
```

`metricField` must match `threshold_field` (the column `assess_severity` evaluates). `baseSeverityValue: 2` is ITSI's `normal` band; `1` = info (used for gap_severity), `-1` = unknown.

### Verify health score propagation

```spl
# 1. KPI values with severity (after indicator run)
| search index=itsi_summary itsi_service_id=<svc_key> NOT alert_value=N/A
| stats latest(alert_level) as level latest(alert_severity) as sev by itsi_kpi_id
| where level != "-1"

# 2. Service health (written by service_health_monitor, runs every 1 min)
| search index=itsi_summary source=service_health_monitor itsi_service_id=<svc_key>
| sort -_time | head 1 | table health_score, alert_level, severity_label
```

Expect `health_score=100.0`, `alert_level=2`, `severity_label=normal` once child KPIs have non-unknown severities.

### Service-template locking

If a service is linked to a `base_service_template_id`, ITSI blocks PATCH of KPI search attributes (`base_search_metric`, thresholds) on the service:

```
Cannot update search attributes for KPI linked to service template...
```

**Fix:** PATCH template KPIs first, then either push template changes (if your ITSI version exposes that API) or temporarily unlink the service (`base_service_template_id: ""`), PATCH service KPIs, and **do not** re-link via the standard service PATCH if ITSI rejects re-linking (HTTP 400 on a lab instance). Keep template KPI defs in sync for greenfield deploys.

### Force indicator write to itsi_summary

Manual `dispatch` without alert actions shows correct severity in the **job results** but does not update `itsi_summary`. Indicators use `action.indicator=1` (not `action.summary_index`).

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "output_mode=json" \
  --data-urlencode "trigger_actions=1" \
  "$ITSI_URL/servicesNS/nobody/itsi/saved/searches/Indicator%20-%20Shared%20-%20<BASE_SEARCH_KEY>%20-%20ITSI%20Search/dispatch"
```

Always pass **`trigger_actions=1`** in deploy/validation scripts. Scheduled cron runs trigger actions automatically.

## The shared-base-search trap (silent rollback)

This is the single biggest gotcha. The pattern:

1. You GET the service to inspect a KPI
2. You modify a field (e.g., set `is_service_entity_filter=true`)
3. You PATCH the service with the modified `kpis` array using `is_partial_data=1`
4. PATCH returns 200 OK
5. You GET the service again — the field didn't change

What happened: ITSI validates the entire `kpis` array. If ANY KPI in the array has an invalid field, the WHOLE array is silently reverted to the previous state. The 200 OK refers to the service object metadata being accepted, NOT the kpis array contents.

## Deleting a KPI — `is_partial_data=1` MERGES the array, it does NOT remove entries

Another silent trap, discovered the hard way (it created duplicate KPIs across two services):

- `POST /service/{key}?is_partial_data=1` with a **reduced** `kpis` array **merges by `_key`** — it adds/updates the KPIs you send, but does **not delete** the ones you omitted. The POST returns 200 and a naive `len(before) - len(kept)` diff makes it *look* like a removal happened, but the omitted KPIs stay put (and keep emitting to `itsi_summary`).
- This is the correct behaviour for *adding/editing* (it's why `is_partial_data=1` is safe for field edits — it won't clobber `description`, `entity_rules`, `services_depends_on`). It is the *wrong* tool for **removal**.

**To actually remove a KPI from a service**, do a **full-object round-trip** (no `is_partial_data`, or `is_partial_data=0`):

```python
svc = http_get(f".../service/{sid}")            # full object
svc = svc[0] if isinstance(svc, list) else svc
svc["kpis"] = [k for k in svc["kpis"] if k["title"] not in TO_REMOVE]
http_post(f".../service/{sid}", coerce(svc))    # FULL replace -> the shrink persists
```

Because it's a full replace, send the *entire* round-tripped object (all fields) and apply the usual numeric→string `coerce()`. Verify with a GET afterwards — and, if the KPIs were emitting, confirm the stale `serviceid` stops appearing in `itsi_summary` (old rows age out; no *new* rows should be written).

> Migrating KPIs between services = **copy (partial add) to the target, then full-object POST to strip them from the source.** Don't trust the partial delete.

### The two most common validators that trip this

#### Trap 1: emptying the `search` field on a shared-base KPI

When you clone a KPI from another service, you might cargo-cult delete fields that look like they shouldn't be there (e.g., `search`, `search_type_options`, `search_alert_earliest`). For shared-base KPIs, these get computed from the referenced base search at runtime — but ITSI's validator still requires them to be present at write time (it doesn't recompute them as part of the validation).

**Fix**: when modifying a shared-base KPI, leave the `search`, `search_alert`, `search_buckets`, `search_occurrences`, `search_time_compare`, `search_time_series` fields alone if they're already populated. If you're creating a new KPI from scratch:

```python
# Pull the base search to get the canonical search string
bs = http_get(f"/servicesNS/nobody/SA-ITOA/itoa_interface/kpi_base_search/{base_search_id}")
canonical_search = bs['base_search']  # the full SPL string

new_kpi = {
    "_key":             str(uuid.uuid4()),
    "title":            "CPU Utilization",
    "search_type":      "shared_base",
    "base_search_id":   base_search_id,
    "base_search_metric": "m_cpu",
    # These get derived from base at runtime, but must be present for validation:
    "search":           canonical_search,
    "search_alert":     canonical_search,
    "search_buckets":   bs.get('search_buckets', ""),
    # ... other entity binding fields ...
}
```

Easier path: clone an existing working KPI from the same service (or another service with the same base search). Use `copy.deepcopy()` and modify only the fields you need to change. All the boilerplate `search*` fields come along correctly.

#### Trap 2: a stale/wrong field name in the kpis array

If you accidentally include a typo (`is_service_enity_filter` instead of `is_service_entity_filter`), the whole array is rejected silently. The PATCH says 200, the GET shows nothing changed.

**Fix**: validate field names against a known-good KPI before constructing the payload. A simple diff:

```python
known_good = json.loads(open('working_canary.json').read())  # one good KPI
new_kpi = build_new_kpi(...)
extra = set(new_kpi.keys()) - set(known_good.keys())
missing = set(known_good.keys()) - set(new_kpi.keys())
if extra:
    print(f"WARNING: extra fields in new KPI (may cause rollback): {extra}")
if missing:
    print(f"WARNING: missing fields vs canary: {missing}")
```

### The PATCH-False-doesn't-take quirk

If a service's entity rule includes a valid alias clause (`{field: "ITSIUniqueId", field_type: "alias", value: "*"}`), ITSI auto-reasserts `is_service_entity_filter=True` on all KPIs in the service. PATCH-ing to False appears to succeed but the GET shows True.

This is by design — ITSI knows the alias is available, the filter will work, so it forces it on. Working as intended. If you genuinely need the KPI to show un-filtered data, remove the alias clause from the entity rule (Layer 2), then PATCH the KPI to False (Layer 4).

For the common case (you WANT is_service_entity_filter=True), this auto-reassert is helpful — even if your PATCH payload accidentally omits or mis-types the field, ITSI fixes it.

## The bulk-replication pattern (idempotent)

Real-world setup: you have ONE working canary KPI on ONE service, and you need 6 KPIs on 9 services = 54 KPIs total. Manual UI rollout is ~3 hours; scripted is ~20 seconds.

```python
import json, uuid, copy
import urllib.request, urllib.parse, ssl, os

ITSI_URL = os.environ['ITSI_URL']
TOKEN    = os.environ['ITSI_TOKEN']
CTX      = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
HDR_R    = {'Authorization': f'Bearer {TOKEN}'}
HDR_W    = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

def http(method, path, data=None, headers=None):
    url = f"{ITSI_URL}{path}"
    headers = headers or (HDR_W if data else HDR_R)
    req = urllib.request.Request(url, 
        data=json.dumps(data).encode() if data else None, 
        headers=headers, method=method)
    with urllib.request.urlopen(req, context=CTX) as r:
        return json.loads(r.read())

# 1. Pull the canary - one fully-working KPI as the template
canary_svc = http('GET', f"/servicesNS/nobody/SA-ITOA/itoa_interface/service/{CANARY_SVC_KEY}")
template = next(k for k in canary_svc['kpis'] if k.get('title') == 'CPU Utilization')

# 2. KPI specs - what differs per metric in the same base search
KPI_SPECS = [
    {"title": "CPU Utilization",   "base_search_metric": "m_cpu",    "threshold_field": "sa_cpu_utilization",  "unit": "%"},
    {"title": "Memory Free",       "base_search_metric": "m_mem",    "threshold_field": "sa_memory_free_mb",   "unit": "MB"},
    {"title": "Disk Read IOps",    "base_search_metric": "m_diskr",  "threshold_field": "sa_disk_read",        "unit": ""},
    {"title": "Disk Write IOps",   "base_search_metric": "m_diskw",  "threshold_field": "sa_disk_write",       "unit": ""},
    {"title": "Network Rx",        "base_search_metric": "m_netrx",  "threshold_field": "sa_network_receive",  "unit": ""},
    {"title": "Network Tx",        "base_search_metric": "m_nettx",  "threshold_field": "sa_network_send",     "unit": ""},
]

# 3. Target services - the leaves to receive the KPI set
TARGETS = [
    ("e84db4fd-68d2-42cf-aafe-4c0ec402cf7e", "Middleware-Queue - Platform"),
    ("a1eda1a0-9052-4c17-a707-b43560eac11e", "Invoicing-App - Platform"),
    # ... 6 more ...
]

def default_thresholds(metric_field: str) -> dict:
    return {
        "baseSeverityColor": "#5fbf7fff",
        "baseSeverityColorLight": "#5fbf7f33",
        "baseSeverityLabel": "normal",
        "baseSeverityValue": 2,
        "gaugeMax": 100, "gaugeMin": 0,
        "isMaxStatic": False, "isMinStatic": True,
        "metricField": metric_field,
        "renderBoundaryMax": 100, "renderBoundaryMin": 0,
        "thresholdLevels": [],
    }

for svc_key, svc_title in TARGETS:
    svc = http('GET', f"/servicesNS/nobody/SA-ITOA/itoa_interface/service/{svc_key}")
    
    # Idempotency: which KPIs already exist by title?
    existing_titles = {k.get('title') for k in svc.get('kpis', [])}
    
    new_kpis = []
    for spec in KPI_SPECS:
        if spec['title'] in existing_titles:
            print(f"  skip {spec['title']} (already exists on {svc_title})")
            continue
        clone = copy.deepcopy(template)         # carries all boilerplate fields
        clone['_key']               = str(uuid.uuid4())   # FRESH key per service
        clone['title']              = spec['title']
        clone['base_search_metric'] = spec['base_search_metric']
        clone['threshold_field']    = spec['threshold_field']
        clone['unit']               = spec['unit']
        thresh = default_thresholds(spec['threshold_field'])
        clone['aggregate_thresholds'] = thresh
        clone['entity_thresholds']    = thresh
        clone['kpi_threshold_template_id'] = ''
        new_kpis.append(clone)
    
    # Build entity_rules (Layer 2) for this leaf
    entity_rules = [{
        "rule_condition": "AND",
        "rule_items": [
            {"field": "ITSIUniqueId", "field_type": "alias", "rule_type": "matches", "value": "*"},
            {"field": "service",      "field_type": "info",  "rule_type": "matches", "value": svc_title.lower()}
        ]
    }]
    
    # Merge: existing kpis + new clones, plus entity_rules
    payload = {
        "kpis": list(svc.get('kpis', [])) + new_kpis,
        "entity_rules": entity_rules
    }
    
    res = http('POST', f"/servicesNS/nobody/SA-ITOA/itoa_interface/service/{svc_key}?is_partial_data=1", payload)
    print(f"  {svc_title:35s} - added {len(new_kpis)} KPIs (total now {len(payload['kpis'])})")
```

Key idempotency properties:
- Re-running this script on a partially-completed rollout skips already-existing KPIs (matched by title)
- Generates fresh UUIDs per service (don't share `_key` across services!)
- Preserves the ServiceHealthScore KPI (it's in `svc['kpis']`, included in the merge)
- Preserves any pre-existing KPIs (e.g., a manually-tweaked one)
- Overrides `entity_rules` — if this is unwanted on services that already have custom rules, gate with `if not svc.get('entity_rules'): payload['entity_rules'] = entity_rules`

## GUI ↔ REST mapping for KPI fields

The GUI uses friendlier names. The mapping when debugging via the UI:

| GUI label (Service Configuration → KPI) | REST field |
|---|---|
| KPI Name | `title` |
| KPI Description | `description` |
| Source → "Use a base search shared across KPIs" | `search_type: "shared_base"` |
| Base Search dropdown | `base_search_id` |
| Metric dropdown | `base_search_metric` |
| "Enable Entity Breakdown" checkbox | `is_entity_breakdown` |
| "Entity Split Fields" (when expanded) | `entity_breakdown_id_fields` |
| "Filter to entities assigned to this service" | `is_service_entity_filter` |
| "Statistics Field" | `threshold_field` |
| "Unit" | `unit` |
| "Aggregate Thresholds" / severity bands | `aggregate_thresholds` |
| "Entity Thresholds" | `entity_thresholds` |
| "Fill Gaps" radio | `fill_gaps`, `gap_severity*` |
| "Apply Threshold Template" | `kpi_threshold_template_id` |

## Units that get blanked

ITSI enforces a controlled vocabulary on the `unit` field. If you set anything outside this list, it persists in the API response but renders blank in the UI:

| Renders correctly | Renders blank |
|---|---|
| `%`, `MB`, `GB`, `KB`, `B`, `ms`, `s`, `min`, `hr`, `MS/s`, `KB/s`, `MB/s`, `GB/s`, `bps`, `Kbps`, `Mbps`, `Gbps`, `count`, `ops`, `Hz`, `KHz`, `MHz`, `GHz` | `ops/s`, `B/s`, `iops`, `IOPS`, `MB/sec`, `req/s`, custom anything |

For non-supported units, leave blank and embed the unit in the KPI title:
- "Disk Read IOps" (unit blank)
- "Network Rx (B/s)" (unit blank)

Cosmetic only — the KPI works either way.

## One unit per KPI — the aggregate tile and the entity breakdown SHARE it

A KPI has exactly **one** `unit` field, and ITSI applies it to *both* the service-aggregate
tile *and* every split-by / entity-breakdown row. There is **no per-level unit override**.
This is a hard ITSI limitation, not a payload trick you can work around.

The trap: overloading one KPI so the aggregate and the entity level measure *different things*.
Classic example (a parked-invoice KPI split by `DOC_GUID`):
- aggregate wanted = **count** of parked invoices (`aggregate_statop=count`)
- per-entity wanted = **minutes** each invoice has been parked (`entity_statop=max` on a `stuck_min` field)

That is two different units (count vs min) on one KPI. Whatever single `unit` you pick is wrong
at one of the two levels (`939 min` at the tile, or `1437 count` in the breakdown). It is *also*
a threshold-semantics mismatch: aggregate thresholds grade a count while entity thresholds grade
minutes.

### Fix: split into two unit-consistent KPIs (same base search, two metrics)

ITSI computes stats at the **base-search metric** level, so two KPIs that need different
`aggregate_statop`s must point at **two different metrics** — you cannot get `count` and `avg`
from the same metric by only changing the KPI-level statop (the base-search metric is
authoritative for the generated indicator search; the KPI-level statop is denormalized).

One base search, two metrics on the same `threshold_field`:

```python
# metric A — minutes (entity story)
{"_key":"stuck_min",    "title":"Parked Invoice Age (min)", "unit":"min",
 "aggregate_statop":"avg",   "entity_statop":"max",   "threshold_field":"stuck_min"}
# metric B — count (rollup story)   (count applied to the same field just counts rows)
{"_key":"parked_count", "title":"Parked Invoices",          "unit":"count",
 "aggregate_statop":"count", "entity_statop":"count", "threshold_field":"stuck_min"}
```

Two KPIs, each internally unit-consistent:

| KPI | base_search_metric | is_entity_breakdown | aggregate_statop | unit | tile shows | breakdown shows |
|---|---|---|---|---|---|---|
| Parked Invoices | `parked_count` | **False** | count | `count` | `939 count` | (none) |
| Parked Invoice Age (min) | `stuck_min` | **True** (`DOC_GUID`) | avg | `min` | `740 min` | per-invoice `15.5 … 1437.7 min` |

Notes:
- The count KPI keeps `is_entity_breakdown=False` even though the base search is entity-broken-down;
  it rolls the per-`DOC_GUID` rows up to a single count. Breakdown OFF also means it produces
  **no per-entity severities**, so it can never trip the entity-degraded correlation search.
- The age KPI's aggregate is `avg(stuck_min)` = minutes, so tile and rows are both minutes → one
  unit (`min`) is correct at both levels.
- If a single KPI is unavoidable, the only honest option is `unit` blank + semantics in the title
  (e.g. `Parked Invoices — count · entity: min`); the breakdown numbers then carry no visible unit.

Rule of thumb: **if the aggregate and the entity level answer different questions, that's two KPIs.**

### Corollary — N KPIs, one column, different statops = N base-search metrics

Same root cause, generalised. If several KPIs read the **same base-search column** but need
**different `aggregate_statop`s**, give each its own metric `_key` (all pointing at the same
`threshold_field`). ITSI syncs every KPI's statop *from its linked base-search metric*, so if
two KPIs share one metric they silently collapse to that metric's statop.

Validated (invoice-processing use case, 2026-07): one per-vendor base search column `inv_count` feeds three KPIs —

```python
{"_key":"inv_count",      "threshold_field":"inv_count", "aggregate_statop":"sum"},   # Total Invoices
{"_key":"vendors",        "threshold_field":"inv_count", "aggregate_statop":"count"}, # Distinct Vendors (counts rows)
{"_key":"inv_per_vendor", "threshold_field":"inv_count", "aggregate_statop":"avg"},   # Invoices per Vendor
```

First attempt pointed all three at `inv_count` and set the statop on the KPI object; after the
service save the readback showed **all three = `sum`** (the base metric's statop won). Separate
metric `_key`s fixed it. Verify by reading back `aggregate_statop` from the service, not from your
payload.

### Gotcha — repointing an existing KPI to a different base search lags (assess_severity lookup)

If you change an existing KPI's `base_search_id`/`base_search_metric` (rather than creating a
fresh KPI on the target base search), the KPI object updates immediately but the KPI→base-search
association that the `assess_severity(<base>)` macro resolves **at indicator runtime** is rebuilt
by ITSI's async refresh job. Symptoms for several minutes (worse under scheduler concurrency load):

- The **old** base search's indicator keeps emitting the KPI (aggregate-only, `entity_title=service_aggregate`).
- The **new** indicator's generated SPL already computes the new `alert_value_*` columns, but
  `assess_severity` only emits KPIs that were *born* on that base search — repointed ones are missing.
- `itsi_summary … | stats values(kpibasesearch) by kpi` still shows the KPI under the OLD base key.

It self-heals once the refresh completes and a couple of cron cycles run — no fix needed, just
**verify via the `kpibasesearch` field in `itsi_summary`**, not just the KPI config readback.
Dispatching the new indicator early runs the pre-refresh version, so wait for the refresh before
trusting a manual dispatch. (Creating new KPIs on the base search does not have this lag.)

## Pseudo-entity investigation: episode dashboard via a custom NEAP (not Service Analyzer)

**Validated pattern (ITSI 4.21.2, 2026-07).** When a KPI is broken down by a
split-by field (pseudo-entities — e.g. `DOC_GUID`, `VENDOR_NO`) rather than real
entity-store objects, you get per-value severities in `itsi_summary` for free, and the
built-in `Service Monitoring - Entity Degraded` correlation search raises a notable per
degraded pseudo-entity (with `entity_title` = the split value). But you hit a wall when a
user wants to **click a pseudo-entity and drill into its detail**:

- **Service Analyzer gap (cannot be fixed):** the entity-breakdown view has a *Drilldown*
  column, but it is populated from the **entity type's** `dashboard_drilldowns`, which only
  resolve for **real** entities (an entity-store record with `entity_type`). Pseudo-entities
  have no entity record, so the Drilldown column stays empty. This is an ITSI limitation —
  there is no per-pseudo-entity drilldown in Service Analyzer. Accept it. (Enhancement request
  filed: **ITSIID-I-479** on ideas.splunk.com — "Enable drilldown dashboards / navigation links
  for pseudo-entities in the Service Analyzer".)
- **Episode Review works (the substitute):** wire the drilldown at the **episode** layer via
  a custom **Notable Event Aggregation Policy (NEAP)**. The NEAP field **`group_dashboard`**
  holds an **inline Dashboard Studio JSON** that renders as a tab *inside* the episode, and
  **`group_dashboard_context`** (`"first"`/`"last"`) selects which notable's fields populate
  tokens — so `$entity_title$` (the pseudo-entity value) and `$itsi_group_id$` are available
  to the embedded dashboard's searches. This gives a per-item health/detail dashboard exactly
  where an analyst investigates.

Why this is the right trade-off: pseudo-entities are **far lighter** than creating thousands
of real, short-lived entities (no entity-store churn, no aggressive housekeeping policy, no
import cadence). You keep the count/aggregate KPI + entity-level thresholds, and recover the
"click to investigate" experience in Episode Review.

### Recipe

1. **Never edit stock content** (see `splunk-itsi-safety-guidelines`): do **not** repoint the
   single URL drilldown on the stock `Service Monitoring - Entity Degraded` correlation search
   — it is shared by every service's episodes. Create a **new, scoped** NEAP instead.
2. NEAP config (POST to `event_management_interface/notable_event_aggregation_policy`):
   - `filter_criteria` → clause AND: `serviceid = <SVC_KEY>` **and** `kpi = "<KPI title>"`
     (tight scope so only this KPI's pseudo-entity notables are claimed).
   - `split_by_field` → `entity_title` → one episode per pseudo-entity.
   - `group_dashboard` → `json.dumps(<DS-JSON>)`; `group_dashboard_context` → `"last"`.
   - `priority` → above the default catch-all (`5`). (Priority only breaks ties; see multi-assign note.)
   - `breaking_criteria` → pause + break on `severity=2` (normal) so episodes self-close on recovery.
3. In the embedded DS JSON, drive dataSources off `$entity_title$` and add a
   `drilldown.customUrl` link to the full standalone dashboard,
   e.g. `/app/itsi/<dashboard_id>?form.<tok>=$entity_title$`.

```python
# minimal group_dashboard (DS Studio JSON) — one search keyed off the pseudo-entity value
gd = {
  "visualizations": {
    "v_events": {"type": "splunk.table", "title": "E2E events for this item",
      "dataSources": {"primary": "ds_ev"}, "options": {"count": 50}},
    "v_open": {"type": "viz.text", "options": {"content": "**Open full dashboard**",
      "link": "true"}, "eventHandlers": [{"type": "drilldown.customUrl",
      "options": {"url": "/app/itsi/invoice_investigation_lab?form.invoice_guid=$entity_title$",
                  "newTab": True}}]},
  },
  "dataSources": {"ds_ev": {"type": "ds.search", "options": {
      "query": '(index=doccapture sim=true "$entity_title$") OR (index=erp sim=true DOC_GUID="$entity_title$") | table _time index sourcetype _raw | sort _time',
      "queryParameters": {"earliest": "-3d", "latest": "now"}}}},
  "layout": {"type": "grid", "options": {}, "structure": [
     {"item": "v_open",   "type": "block", "position": {"x": 0, "y": 0,  "w": 1150, "h": 40}},
     {"item": "v_events", "type": "block", "position": {"x": 0, "y": 40, "w": 1150, "h": 430}}]},
  "title": "Item Investigation", "inputs": {}, "description": ""
}
policy = {"object_type": "notable_aggregation_policy", "title": "Buttercup - Parked Invoice Investigation (Lab)",
  "disabled": 0, "is_default": 0, "priority": 7, "split_by_field": "entity_title",
  "group_dashboard": json.dumps(gd), "group_dashboard_context": "last",
  "filter_criteria": {"condition": "OR", "items": [{"type": "clause", "config": {"condition": "AND", "items": [
     {"type": "notable_event_field", "config": {"field": "serviceid", "operator": "=", "value": SVC_KEY}},
     {"type": "notable_event_field", "config": {"field": "kpi", "operator": "=", "value": KPI_TITLE}}]}}]},
  "breaking_criteria": {"condition": "OR", "items": [{"type": "pause", "config": {"limit": "7200"}},
     {"type": "clause", "config": {"condition": "AND", "items": [
        {"type": "notable_event_field", "config": {"field": "severity", "operator": "=", "value": "2"}}]}}]},
  "group_title": "Parked invoice %entity_title%", "group_severity": "%severity%",
  "group_status": "%status%", "group_assignee": "%owner%", "group_description": "%description%", "rules": []}
```

### NEAP multi-assign — priority does NOT dedupe episodes

ITSI is **multi-assign**: *every* enabled policy whose `filter_criteria` matches a notable
independently creates its own episode. `priority` only picks a single winner in single-assign
tie-breaks; it does **not** stop a broad policy from also firing. Consequence on stacks that
ship the "Monitoring & Alerting" content pack with **all three** example policies enabled
(`…-episodes-by-alarm`, `…-by-src`, `…-by-itsi-service`, each `priority=''`, catch-all filter):
one degraded pseudo-entity produces ~4 episodes — one under your scoped policy (with the
`group_dashboard`) and three duplicates under the CP policies (**without** it). The user must
open **your** policy's episode to see the tab.
- To verify which policy owns an episode: `index=itsi_grouped_alerts serviceid=<SVC> | stats count values(title) by itsi_policy_id` (KV field is `itsi_policy_id`; the aggregation-policy `_key` is what you match).
- To make episodes 1:1 you must reduce the overlapping policies — and per the never-edit-stock
  rule that means **clone the CP policy you want, add an exclusion filter, disable the stock
  original** (clone→edit→verify→disable), not editing the shipped policy in place. Only do this
  with explicit approval — disabling CP policies is stack-wide.

## When to use search_type=adhoc instead of shared_base

Default: shared_base. Use adhoc only when:

- The KPI is a one-off that no other KPI will share
- The base search depends on macros or fields not exposed in any reusable search
- You're prototyping a metric and don't want to pollute the base search registry

Adhoc payload differences:
```json
{
  "search_type":  "adhoc",
  "search":       "| mstats ...",
  "search_alert": "| mstats ...",  // usually identical to search
  // base_search_id and base_search_metric NOT used
}
```

Same Layer 4 settings apply (`is_service_entity_filter`, `entity_*_id_fields`).

## Force-refresh after a KPI change

ITSI's scheduled-search infrastructure takes ~1 scheduling interval to pick up KPI config changes. To force immediate refresh **and** write severity to `itsi_summary`:

```bash
# Shared-base-search KPIs (one indicator per base search)
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "output_mode=json" \
  --data-urlencode "trigger_actions=1" \
  "$ITSI_URL/servicesNS/nobody/itsi/saved/searches/Indicator%20-%20Shared%20-%20<BASE_SEARCH_KEY>%20-%20ITSI%20Search/dispatch"

# Per-KPI adhoc indicators (legacy / non-shared-base)
KPI_SAVED_SEARCH="Indicator - kpi=<KPI _key>"
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "trigger_actions=1" \
  "$ITSI_URL/services/saved/searches/$KPI_SAVED_SEARCH/dispatch"
```

Without `trigger_actions=1`, the dispatch job may return rows with correct `alert_severity` but **`itsi_summary` stays stale** until the next scheduled run.

Or via UI: open the service, open the KPI settings, save (no change needed). ITSI re-dispatches the underlying search on every KPI save.

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Reusing the same `_key` across services when cloning | Second service's PATCH succeeds but its KPI shows as the first service's (KV store key collision) | Generate fresh UUID per service: `clone['_key'] = str(uuid.uuid4())` |
| Forgetting `?is_partial_data=1` on the PATCH | PATCH replaces the entire service object; loses `description`, `entity_rules`, `services_depends_on`, etc. | Always include `?is_partial_data=1` for field-level edits |
| **Removing a KPI with `?is_partial_data=1` + a reduced `kpis[]`** | POST 200 but the omitted KPI is NOT deleted (array merges by `_key`); leaves duplicates emitting to `itsi_summary` | To delete, do a **full-object POST** (no `is_partial_data`) with the shrunk `kpis[]`. See "Deleting a KPI" section |
| Dropping the ServiceHealthScore KPI from the kpis array in the merge | Service Health stops calculating; rolls up as gray | Always include ALL existing KPIs in the PATCH payload, including SHKPI-* |
| Clearing the `search` field on a shared-base KPI | PATCH 200, but kpis array silently rolled back | Leave existing `search*` fields alone, or populate them from the base search's `base_search` field |
| Using `metric_name` instead of `_key` for `base_search_metric` | KPI shows no data; base_search_metric reference is invalid | The base search metric reference is by `_key` (e.g., `"m_cpu"`), not display name. Check `kpi_base_search.metrics[].{_key,title}` |
| Setting `is_entity_breakdown=true` on the KPI but `false` on the base search | KPI shows aggregate only | Both must agree. Easier to set on base search only and inherit |
| Threshold templates referenced by `kpi_threshold_template_id` that don't exist | PATCH succeeds but KPI shows no severity colors | Use empty string for "no template"; verify any template _key exists before referencing |
| **No `aggregate_thresholds` / `entity_thresholds` and no template** | KPI values populate; `alert_level=-1`; health_score=N/A in Service Analyzer | Ship `default_thresholds(threshold_field)` on every KPI at deploy time (see above) |
| Dispatching indicator without `trigger_actions=1` | Job results look correct but `itsi_summary` / health scores unchanged | Always pass `trigger_actions=1` on manual dispatch |
| PATCHing KPI thresholds on a template-linked service | HTTP 400: "Cannot update search attributes for KPI linked to service template" | PATCH template KPIs; unlink service or use template-push API before service-level KPI edits |
| Setting `unit` to something not in the controlled list | Unit renders blank in UI even though API stored it | Use controlled list values; otherwise leave blank and embed in title |
| Forgetting to set `enabled: 1` on a new KPI | KPI appears in service but never runs | Set `enabled: 1` explicitly when creating new KPIs |
| Bulk-rolling out KPIs before validating the canary | All 54 KPIs are misconfigured the same way | Always validate one canary in the UI before scripting the rollout. ~10 min upfront saves ~1 hour cleanup |

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| One base search per service (e.g., "Middleware-Bus CPU search", "Fulfilment-Orders CPU search") | N×M searches; wastes search head; impossible to fix universally | One base search per data source + entity type. All services share it |
| Manual UI clicking for 50+ KPIs | 3+ hours; error-prone; not reproducible | Validate one canary in UI, then bulk-replicate via script |
| Treating REST PATCH as "fire and forget" without GET-after-PATCH | Silent rollbacks go undetected until users complain | Always GET after PATCH on the first few iterations; once you know the payload is clean, can skip |
| Embedding site-specific values in the base search (e.g., `index=buttercup_*`) | Not reusable across deployments; needs forking per project | Keep base searches generic; use macros for site-specific filters |
| Deploying KPIs with no inline thresholds and no template | Health scores never appear; easy to miss because KPI values look fine | Always include baseline `aggregate_thresholds` + `entity_thresholds` at deploy; tune bands later |
| Waiting days before any threshold config "to see the data first" | Service Analyzer stays gray for the entire soak period | Baseline normal thresholds are safe; they don't create false criticals. Add warning/critical bands after observing distributions |
| Creating KPIs with `search_type=adhoc` "to be safe" | Loses shared-base benefits (run-once, share-config); harder to maintain | Default to shared_base; switch to adhoc only when there's a specific reason |
| Trying to delete the ServiceHealthScore KPI | Service Health Score is auto-managed by ITSI; deletion attempts return errors or break the service | Never touch SHKPI-* KPIs. They're system-managed |

## Related skills

- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities (prereq)
- `splunk-itsi-entity-binding-architecture` — the 4-layer chain that explains WHY each KPI field matters
- `splunk-itsi-entity-cmdb-lookup` — the upstream that drives the `service` info field used in Layer 2 rules
- `splunk-itsi-service-tree-design` — the service tree these KPIs hang off of
