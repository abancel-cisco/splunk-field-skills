---
name: splunk-itsi-entity-binding-architecture
category: itsi
description: The complete 4-layer chain that makes ITSI KPIs actually scope to the right entities under a service. Covers how (1) the entity import populates the entity store with the right identifier/alias and informational fields, (2) the service entity rules combine an alias-type "matches *" clause with info-type business-attribute clauses to both bind and key entities, (3) the KPI base search exposes `entity_alias_filtering_fields` so ITSI can auto-inject a filter clause, and (4) the per-KPI `is_service_entity_filter=True` flag triggers that injection. Explains why omitting any one layer produces the classic pseudo-entity / aggregate-only-populating / no-real-entities-shown failure modes. Use when designing or debugging service-scoped infrastructure KPIs in ITSI, when entities are showing up in the service but KPIs aren't producing per-entity data, when "aggregate populates but entities don't", when a KPI is leaking data from hosts outside the service, when porting OS Hosts patterns from Azure VM, or when the user mentions entity binding, entity filtering, is_service_entity_filter, entity_alias_filtering_fields, ITSIUniqueId, or service-to-entity scoping in ITSI.
disable-model-invocation: true
---

# ITSI Entity Binding Architecture

The full chain that scopes a KPI to "only the entities that belong to this service." If any one of the four layers is misconfigured, you get one of three failure modes:

1. **No entities at all under the service** — entity rule never matched, or matched on a field that doesn't exist on the entities.
2. **Entities appear in the service, but the KPI shows only the aggregated value (no per-entity breakdown)** — entity rule matched, but the base search doesn't break by the right field, or the per-KPI filter flag is off.
3. **KPI shows ALL hosts in the data, not just the ones bound to the service** — base search and KPI are wired but `is_service_entity_filter` is `False`, so the entity filter clause is never injected.

## When to use this skill

- Designing a service-scoped infrastructure KPI in ITSI (CPU/memory/disk/network on a perimeter or app)
- Debugging "the aggregate value populates but real entities are not found" (the classic symptom)
- Porting a working pattern from one entity type to another (e.g., the SIM Azure VM service works, OS Hosts equivalent doesn't)
- The user mentions `is_service_entity_filter`, `entity_alias_filtering_fields`, `ITSIUniqueId`, "entity binding", "entity filtering"
- A KPI is leaking data from outside the service (showing too many hosts)
- The same physical host appears under multiple services and we want different KPI sets per service

## The 4 layers

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — ENTITY IMPORT                                                      │
│  Writes one row per entity into itsi_entities with:                            │
│    title              <- displayed in topology                                 │
│    identifier.fields  <- the IDENTIFIER FIELDS used by ITSI's matcher          │
│    identifier.values  <- the actual host identifier(s)                         │
│    informational.*    <- business attributes (perimeter, service, app...)     │
│  CRITICAL: the alias field used downstream (e.g. ITSIUniqueId) MUST be in     │
│  identifier.fields, and its value MUST match what the metric stream produces  │
│  for the breakdown field in Layer 3.                                          │
└───────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — SERVICE ENTITY RULES                                               │
│  service.entity_rules = [{                                                     │
│    rule_condition: "AND",                                                      │
│    rule_items: [                                                               │
│      { field: "ITSIUniqueId", field_type: "alias", rule_type: "matches",       │
│        value: "*" },              <-- THE KEYSTONE. tells ITSI which alias    │
│                                       to use as the entity↔data join key      │
│      { field: "service",       field_type: "info",  rule_type: "matches",      │
│        value: "middleware-bus - platform" }   <-- business-attribute selector       │
│    ]                                                                           │
│  }]                                                                            │
│  Both clauses are required:                                                    │
│   - the alias-* clause makes the per-KPI filter mechanism wirable             │
│   - the info clause is what actually scopes WHICH entities are bound          │
└───────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — KPI BASE SEARCH                                                    │
│  kpi_base_search settings:                                                     │
│    is_entity_breakdown:              true                                      │
│    entity_breakdown_id_fields:       ITSIUniqueId    <- split-by alias        │
│    entity_id_fields:                 ITSIUniqueId    <- join-back alias       │
│    entity_alias_filtering_fields:    ITSIUniqueId    <- ENABLES the auto-     │
│                                                          injected WHERE clause│
│  base_search:                                                                  │
│    | mstats ... by host.name                                                   │
│    | rename host.name as ITSIUniqueId                                          │
│    | dedup _time, ITSIUniqueId                                                 │
└───────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — PER-KPI FILTER FLAG                                                │
│  kpi.is_service_entity_filter: True                                            │
│  Without this flag set to True on the KPI, ITSI does NOT inject the           │
│  entity-list filter clause into the base search — even if Layer 3 has         │
│  entity_alias_filtering_fields set.                                            │
│                                                                                │
│  Setting this via REST PATCH WORKS — earlier "API drops the bool" reports     │
│  were caused by validation failures elsewhere in the payload (e.g. wiping     │
│  the `search` field). When the PATCH is otherwise clean, True persists.       │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Failure modes mapped to layers

| Symptom in Service Analyzer | Likely broken layer | What to check |
|---|---|---|
| Service has **0 entities** | Layer 2 (info clause wrong) | `info.<field>` value vs `_itsi_informational_lookups` on actual entities. ITSI lowercases values on import — match on lowercase |
| Service has **wrong entities** (too many or too few) | Layer 1 (info field missing or wrong) **OR** Layer 2 (rule too broad) | Inspect a few entities: do they have the expected `info.<field>` value? If yes, your rule value is wrong; if no, the import is the problem |
| Service has correct entities but **KPI shows aggregated only** (no per-entity breakdown) | Layer 3 (`is_entity_breakdown=false` or `entity_breakdown_id_fields` wrong) | The split field must exist as a column in the base search output and match the alias the entities expose |
| Service has correct entities, KPI shows per-entity, but **values bleed in from hosts outside the service** | Layer 4 (`is_service_entity_filter=False`) | Toggle the flag — UI or REST PATCH both work as long as you don't break validation elsewhere |
| KPI ran with entity filter previously but now shows aggregated only | Layer 2 (alias clause `ITSIUniqueId matches *` was removed/missing) | The alias clause is what tells ITSI **which alias to use** when injecting the filter. Without it, the filter has no key and silently falls back to "no filter, aggregate only" |
| "Pseudo entities" (synthetic names like `unknown_host` or hash-suffixed) showing under the service | Layer 1 (identifier/alias mismatch with data) | Inspect `identifier.values` on the bound entities; verify the value matches what `by host.name` (or your equivalent) produces in the base search |
| **Only `SHKPI-*` rows appear in `itsi_summary`, zero real KPI rows** (both aggregate and entity) | Layer 1/2 membership not resolved when the indicator was generated | The generated indicator derives `serviceid` via `match_entities(<alias>, sec_grp)` then `mvexpand serviceid`. If entity→service membership isn't resolved, `serviceid=null` → every KPI row is dropped, leaving only the health monitor's `SHKPI-*` rows. Confirm membership on the **entity** object (`services` count > 0), then re-save the base search to force indicator regeneration and wait for the next **scheduled** run. See multi-service worked example below |

## Worked example: Middleware-Bus Platform service (OS Hosts SIM data)

### Layer 1 — Entity import populates this on each host

```json
{
  "title": "mwhost01.example.com",
  "entity_type": "OS Hosts",
  "identifier": {
    "fields": ["ITSIUniqueId", "SignalFxCloudServiceId", "host_name"],
    "values": ["mwhost01.example.com", "mwhost01.example.com", "mwhost01.example.com"]
  },
  "_itsi_informational_lookups": [
    "service::middleware-bus - platform",
    "perimeter::middleware",
    "application::businessworks",
    "..."
  ]
}
```

Notes:
- `ITSIUniqueId` is in `identifier.fields` — this is what enables it to act as an alias-type rule field
- `service::middleware-bus - platform` is lowercase — ITSI lowercases info-field values at import time
- The `ITSIUniqueId` value equals the clean host name, with no hash suffix appended

### Layer 2 — Service entity rule

```json
{
  "entity_rules": [
    {
      "rule_condition": "AND",
      "rule_items": [
        { "field": "ITSIUniqueId", "field_type": "alias", "rule_type": "matches", "value": "*" },
        { "field": "service",      "field_type": "info",  "rule_type": "matches", "value": "middleware-bus - platform" }
      ]
    }
  ]
}
```

The `service` value is **lowercased to match the import**. The display name in the GUI looks like mixed case — ITSI handles the case-fold automatically on UI display but the stored value (and the rule value) must be lowercase.

In the GUI, this rule reads:
- **Service Split Field(s)**: `ITSIUniqueId`
- **Service matches entities on fields**: `service, ITSIUniqueId`
- **Data filtered by service entities in field**: `ITSIUniqueId`

### Layer 3 — Generic SIM OS Hosts base search

The full base search body for a SIM-fed OS Hosts service. Reusable across deployments — nothing site-specific:

```spl
| mstats 
    avg("cpu.utilization")  as sa_cpu_utilization, 
    sum("memory.free")      as sa_memory_free, 
    avg("disk_ops.read")    as sa_disk_read, 
    avg("disk_ops.write")   as sa_disk_write, 
    avg("if_octets.rx")     as sa_network_receive, 
    avg("if_octets.tx")     as sa_network_send 
  where `itsi-cp-observability-indexes` AND cluster!=* 
  by host.name span=5m
| eval sa_memory_free_mb = sa_memory_free / 1024 / 1024
| rename host.name as ITSIUniqueId
| dedup _time, ITSIUniqueId
```

Settings on the `kpi_base_search` object:
```json
{
  "is_entity_breakdown":           true,
  "entity_breakdown_id_fields":    "ITSIUniqueId",
  "entity_id_fields":              "ITSIUniqueId",
  "entity_alias_filtering_fields": "ITSIUniqueId",
  "metric_qualifier":              ""
}
```

And the metric definitions (one per KPI exposed):
```json
"metrics": [
  { "_key": "m_cpu",    "title": "CPU Utilization",  "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_cpu_utilization",  "unit": "%"  },
  { "_key": "m_mem",    "title": "Memory Free",      "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_memory_free_mb",   "unit": "MB" },
  { "_key": "m_diskr",  "title": "Disk Read IOps",   "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_disk_read",        "unit": ""   },
  { "_key": "m_diskw",  "title": "Disk Write IOps",  "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_disk_write",       "unit": ""   },
  { "_key": "m_netrx",  "title": "Network Rx",       "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_network_receive",  "unit": ""   },
  { "_key": "m_nettx",  "title": "Network Tx",       "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_network_send",     "unit": ""   }
]
```

### Layer 4 — KPI references the base search and metric, with the filter flag on

```json
{
  "_key": "<uuid>",
  "title": "CPU Utilization",
  "search_type": "shared_base",
  "base_search_id":                "<base_search _key>",
  "base_search_metric":            "m_cpu",
  "is_entity_breakdown":           true,
  "entity_breakdown_id_fields":    "ITSIUniqueId",
  "entity_id_fields":              "ITSIUniqueId",
  "is_service_entity_filter":      true,
  "threshold_field":               "sa_cpu_utilization",
  "unit":                          "%"
}
```

The KPI inherits the base search settings but the `is_service_entity_filter` is a per-KPI override. Default is `False` — you must explicitly set it.

## Worked example (multi-service): flow model — N leaf lanes + 1 E2E rollup off ONE shared base search

Validated on ITSI Cloud 5.x, 2026-08-12 (Middleware integration-layer flow). This is the reusable
idiom when you want to model a **flow** (integration interfaces, process steps, pipeline stages) as
several leaf services plus one end-to-end rollup — while staying performance-minimal (**one** base
search + **one** indicator feeds all of them).

### Shape

```
                 ┌──────────── ONE shared base search (BS_Integration_Flow) ────────────┐
                 │  index=flow_db sim=true | ... | stats ... by iface                   │
                 │  is_service_entity_filter=True                                       │
                 └──────────────────────────────┬───────────────────────────────────────┘
                                                │  (one generated indicator search)
        ┌───────────────┬───────────────┬───────┴───────┬──────────────────────────────┐
   Leaf: ORDERS    Leaf: SHIPPING   Leaf: ERP-QA    Leaf: LABS       Rollup: Integration Flow (E2E)
   rule: iface     rule: iface      rule: iface     rule: iface      rule: flow_model matches "flow"
    matches ORDERS  matches SHIPPING matches ERP-QA  matches LABS    (aggregates ALL lane entities)
        │               │                │               │                        │
   entity: "Orders Interface"  ... one REAL entity per lane, each with:
        iface=<lane>        (identifier/alias  → per-lane leaf scoping)
        flow_model=flow     (info tag          → shared key the rollup matches)
```

### The two rules that make it work

- **Each leaf service** matches on the per-lane alias field: `iface matches "<lane>"`. Because
  `is_service_entity_filter=True`, its KPIs are scoped to that one lane's entity only.
- **The E2E rollup service** matches on a **shared info tag** present on *every* lane entity:
  `flow_model matches "flow"`. So it dynamically aggregates all lanes with no hard-coded list — add
  a new interface later and it joins the rollup automatically once tagged.

Each lane entity therefore belongs to **two** services (its leaf + the rollup). That `services=2`
count is your fast membership-resolution check:

```bash
GET /servicesNS/nobody/SA-ITOA/itoa_interface/entity?fields=title,iface,flow_model,services&count=0
# each lane entity → services == 2  (leaf + E2E rollup). 0 or 1 ⇒ membership not resolved yet.
```

### Why you can get "only SHKPI rows, no KPI rows"

The generated indicator SPL ends with the ITSI-standard scoping block:

```spl
... | stats latest(...) AS alert_value_* by iface
| eval serviceid=null() | eval sec_grp="default_itsi_security_group"
| `match_entities(iface, sec_grp)`      <-- fills serviceid from ENTITY→SERVICE membership
| mvexpand serviceid                    <-- null serviceid ⇒ row is DROPPED here
| appendpipe [ ... service_aggregate ... ]
| `assess_severity(<BS>)` | eval itsi_kpi_id=kpiid, itsi_service_id=serviceid
```

`serviceid` comes **only** from `match_entities`, which reads the entity→service membership. If you
created entities/services/KPIs and dispatched before ITSI resolved membership, `serviceid=null` →
`mvexpand` drops every lane row → nothing but the health-monitor `SHKPI-*` rows land in
`itsi_summary`. It self-heals once membership resolves and the indicator regenerates. Force it:
re-save the **base search** (full-object POST) to regenerate the indicator, then wait for the next
**scheduled** run (manual dispatch of ITSI indicators is unreliable — see
`splunk-itsi-kpi-creation-via-api`).

### Diagnose by service id, not by source

`itsi_summary` rows are keyed by `itsi_service_id` / `itsi_kpi_id`, **not** by a `source` that
contains the base-search name. Don't filter `source="*BS_Integration_Flow*"` (returns 0). Instead:

```spl
index=itsi_summary itsi_service_id IN ("<leaf1>","<leaf2>",...,"<e2e>") earliest=-30m latest=now
| stats latest(alert_value) AS v latest(alert_severity) AS sev count by itsi_service_id, itsi_kpi_id
```

Healthy result: each leaf shows its own lane's values; the E2E service shows the sums/worst-of
across lanes; a graded KPI on one lane (e.g. ORDERS backlog `medium`) rolls its severity up into the
E2E rollup's health.

### Performance note

This pattern is deliberately the performance-minimal choice: **one** scheduled base search + **one**
indicator for the whole flow, regardless of how many lanes/leaves. Do **not** create a base search
per lane (that's the N×M anti-pattern in the table below). Keep the base search on a sane
`alert_period` (e.g. 30 min for a 24h-window flow model) so it doesn't add concurrency pressure.

## Debugging checklist (in order)

When a service-scoped KPI is misbehaving, walk the layers in this order — never reverse. Each layer depends on the previous.

```
[ ] 1.  Is the entity bound?
        Query: GET /servicesNS/nobody/SA-ITOA/itoa_interface/service/<key>?fields=entity_keys
        Count > 0 ?  →  if 0, Layer 2 problem.

[ ] 2.  Inspect a bound entity. Does it have ITSIUniqueId in identifier.fields?
        Query: GET /servicesNS/nobody/SA-ITOA/itoa_interface/entity/<entity_key>
        Look at identifier.fields and identifier.values.
        Missing or wrong  →  Layer 1 problem (fix the entity import search).

[ ] 3.  Does the entity have the expected info field at the expected value?
        Same response, look at _itsi_informational_lookups for "service::<your-value>"
        Wrong value  →  Layer 1 (import) OR Layer 2 (rule typo). Compare both.

[ ] 4.  Inspect the kpi_base_search:
        - is_entity_breakdown == true ?
        - entity_breakdown_id_fields == "ITSIUniqueId" (or your alias) ?
        - entity_id_fields == same ?
        - entity_alias_filtering_fields == same ?
        Any missing  →  Layer 3 problem.

[ ] 5.  Run the base search standalone in Splunk's Search UI:
        Does it produce a column named ITSIUniqueId (or your alias)?
        Does the value in that column match the entity identifier.values from step 2?
        Mismatch  →  Layer 1 OR Layer 3 (rename clause wrong in the SPL).

[ ] 6.  Inspect the KPI:
        - search_type == "shared_base" and base_search_id matches the base search _key ?
        - is_service_entity_filter == True ?
        - entity_id_fields and entity_breakdown_id_fields match Layer 3 ?
        Flag false  →  Layer 4. PATCH or UI-toggle.

[ ] 7.  Force-rerun the KPI's scheduled search to pick up the new config:
        UI: open the service, click any KPI, Save (no change). This triggers
        re-dispatch of the underlying scheduled search.
        Or REST: POST /services/saved/searches/<saved_search_name>/dispatch
```

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Missing the alias-type `matches *` clause in the entity rule | Entities bind correctly, but KPI shows only aggregated value (no per-entity); entity filtering doesn't work | Add `{field: "<alias>", field_type: "alias", rule_type: "matches", value: "*"}` as the first rule_item. This is the keystone — it tells ITSI which alias to use as the join key |
| Setting `entity_alias_filtering_fields` on the base search but forgetting the per-KPI flag | KPI shows all hosts in the data, not just service-bound ones | Set `is_service_entity_filter=True` on each KPI individually. The base search setting alone is not enough |
| Renaming the alias in the base search but the entity's identifier doesn't have that alias | Base search produces rows, KPI runs but shows zero entities | The alias name in the base search's `rename ... as ITSIUniqueId` must match a field in the entity's `identifier.fields` |
| ITSI rule value in mixed case (e.g., `"Middleware-Bus - Platform"`) | Rule doesn't seem to match in GUI testing but appears to work in storage | ITSI's rule matching is **case-insensitive** for info fields (despite the GUI displaying mixed case). The stored value is lowercased on import. Match on lowercase to be safe; either works at runtime |
| Patching the KPI via REST with a payload that wipes `search` field | PATCH succeeds (200 OK) but `is_service_entity_filter` doesn't change | Validation failure silently rolls back the change. Include the existing `search` value (or omit the field) when PATCHing other KPI fields |
| Trying to PATCH `is_service_entity_filter=False` on a KPI whose service entity rule has the alias clause | Field stays True after PATCH | ITSI auto-reasserts True when the entity rule includes a valid alias clause. Working as designed |
| Same physical host in two services with two different KPI sets | Both services show the host but KPIs from both leak into each other | This is fine when both services' rules match the host AND both KPIs have `is_service_entity_filter=True`. The per-KPI filter scopes each KPI's data to that service's bound entities only |
| Unit values like `ops/s` or `B/s` set on a KPI but they appear blank in the UI | Unit not displayed | ITSI restricts units to a controlled list (`%`, `MB`, `GB`, `ms`, `s`, etc.). Non-standard values are silently blanked. Cosmetic only |

## Mapping to ITSI GUI labels

When debugging via the GUI, the field names look different than the REST API. The mapping:

| REST API field | GUI label (Service Configuration → Entity Rules section) |
|---|---|
| `entity_rules[].rule_items` with `field_type=alias, value=*` | "Service Split Field(s)" |
| `entity_rules[].rule_items` with `field_type=info` | The "Include entities matching..." conditions (one per row) |
| `entity_alias_filtering_fields` on base search | "Data filtered by service entities in field" (visible per-KPI when shared base search expanded) |
| `is_service_entity_filter` on KPI | "Filter to entities assigned to this service" checkbox in KPI settings |
| Combined `entity_id_fields` from rules + KPI | "Service matches entities on fields" (read-only, shown for verification) |

If the GUI's "Service matches entities on fields" line shows only `service` (missing `ITSIUniqueId`), Layer 2 is missing the alias clause.

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Using the entity's `host_name` info field instead of an alias-type field for filtering | `info` fields are designed for grouping/labeling, not for high-cardinality join keys. ITSI's filter injection logic specifically requires an alias-type field | Always use an alias-type identifier field (`ITSIUniqueId`, `host`, `aws_instance_id`...) for filtering. Reserve info fields for business attributes |
| Creating one base search per service ("custom CPU search for Middleware-Bus", "custom CPU search for Fulfilment") | N services × M metrics = N×M searches, all doing the same `mstats`. Wastes search head, search-scheduler load | One generic base search per data source + entity type (e.g., one for `SIM OS Hosts`, one for `SIM Azure VM`). All services share it. Layer 4 filter scopes each instance |
| Hard-coding the entity list in the KPI search with `| where host IN (...)` | Doesn't update when entities are added/removed; bypasses the entity store; defeats the point of the entity model | Use the entity store + entity rules + `is_service_entity_filter`. The injection happens at search time and always reflects current state |
| Setting `is_entity_breakdown=true` on a base search but `is_entity_breakdown=false` on the KPI | KPI silently shows only aggregate; debugging takes hours | Keep both layers consistent. If you want breakdown, set true on both |
| Using different alias fields in different KPIs of the same service | Each KPI does its own join; some work and some don't | Pick ONE alias per service (per entity_type) and use it consistently — entity rule, base search, all KPIs. Cross-service can use different aliases per type, but within a service stay consistent |
| Modifying an entity directly to "fix" binding instead of fixing the upstream import | Next import overwrites your manual edit | Fix the entity import search and re-run it. Treat the entity store as derived data, not source of truth |
| Fixing all 4 binding layers but omitting KPI thresholds | Per-entity KPI rows populate; Service Analyzer health stays gray (`alert_level=-1`) | Add `aggregate_thresholds` + `entity_thresholds` on every KPI — see `splunk-itsi-kpi-creation-via-api` |
| Enabling **graded** `entity_thresholds` on a high-cardinality split-by / pseudo-entity KPI | Every non-normal pseudo-entity trips the built-in `Service Monitoring - Entity Degraded` correlation search → thousands of notables → Episode Review flood | Keep `entity_thresholds` **flat** (single `normal` band, `thresholdLevels:[]`) until you deliberately want Event Analytics, or put the service in maintenance. See section below |

## Pseudo-entity thresholding & the Episode Review flood

Split-by-field "pseudo-entities" (`is_entity_breakdown=true`, `entity_breakdown_id_fields=<field>`,
`is_service_entity_filter=false`, **no** entity-store objects) are great for per-item metrics without
entity housekeeping. But there is a sharp edge once you add **graded** entity thresholds.

**Mechanism:** ITSI ships an always-on correlation search **`Service Monitoring - Entity Degraded`**
that emits a notable event for *every* entity whose KPI severity is anything other than `normal`.
It does not care whether the entity is real or a pseudo-entity. So a KPI split across, say, 1000
invoices with graded minute-thresholds where 500+ land in low/medium/high/critical will generate
500+ notables per run, which the default aggregation policy groups into hundreds/thousands of
episodes within minutes. (Observed: ~1000 stuck-invoice pseudo-entities → 4177 `Entity Degraded`
notables → 1067 episodes.)

**How to tell it's this:**
```
index=itsi_grouped_alerts | search *<SERVICE_KEY>* | stats count by search_name
# -> "Service Monitoring - Entity Degraded" with a count ~= number of non-normal pseudo-entities
```

**Keep it silent (validating the pattern, not yet doing Event Analytics):**
- Set `entity_thresholds` (and usually `aggregate_thresholds`) to a **flat** block:
  `{"baseSeverityLabel":"normal","baseSeverityValue":2,"metricField":"<threshold_field>","thresholdLevels":[]}`.
  All entities compute `normal` → `Entity Degraded` never matches. Per-entity *values* still populate
  in `itsi_summary` (you keep the breakdown), you just don't grade them.
- Or put the service under **maintenance** for the window you want severities without notables.
- A **count** KPI with `is_entity_breakdown=false` is inherently safe — it has no per-entity
  severities to degrade (pair it with a separate breakdown KPI, see the two-KPI split in
  `splunk-itsi-kpi-creation-via-api`).

**Cleanup after a flood:** close episodes via
`POST /servicesNS/nobody/SA-ITOA/event_management_interface/notable_event_group/<itsi_group_id>?is_partial_data=1`
with `{"status":"5"}` (Closed). Get the group ids from `index=itsi_grouped_alerts | search *<SERVICE_KEY>*
| stats count by itsi_group_id`. Note the `itsi_grouped_alerts` index keeps the *at-index-time* status;
verify the close against the KV store (`.../notable_event_group/<id>` GET → `status`), not the index.

## Related skills

- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities (prereq)
- `splunk-itsi-entity-cmdb-lookup` — how the upstream CMDB CSV drives the `service`/`perimeter` info fields via the entity import
- `splunk-itsi-kpi-creation-via-api` — payload shapes for creating/cloning KPIs, REST PATCH pitfalls, and **default thresholds for health scores**
- `splunk-itsi-service-tree-design` — where this binding architecture fits in the overall service tree (Platform pillars under each perimeter)
- `splunk-itsi-flow-monitoring` — uses the multi-service pattern above to model a transaction/process flow (step services + E2E rollup) for bottleneck detection and step-latency trending
