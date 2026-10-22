---
name: splunk-itsi-entity-binding-architecture
category: itsi
topic: service-modelling
description: >-
  The four-layer chain that makes ITSI KPIs scope to the right entities under a service.
  Covers how the entity import populates the entity store with the right identifier, alias and
  informational fields; how service entity rules combine an alias-type matches-all clause with
  info-type business-attribute clauses to both bind and key entities; how the KPI base search
  exposes entity_alias_filtering_fields so ITSI can auto-inject a filter clause; and how the
  per-KPI is_service_entity_filter flag triggers that injection. Explains why omitting any one
  layer produces the classic pseudo-entity, aggregate-only or no-real-entities-shown failure
  modes. Use when designing or debugging service-scoped infrastructure KPIs, when entities
  appear in the service but KPIs produce no per-entity data, when the aggregate populates but
  entities do not, when a KPI leaks data from hosts outside the service, or when the user
  mentions entity binding, is_service_entity_filter, entity_alias_filtering_fields or
  ITSIUniqueId.
disable-model-invocation: true
---

# ITSI Entity Binding Architecture

**Validated on:** ITSI Cloud 5.x, 2026-08.

Four layers scope a KPI to "only the entities in this service". Break one, get one of three
failure modes.

| Symptom | Broken layer |
|---|---|
| No entities under the service | 2 — rule never matched, or matched a field the entities lack |
| Entities bind, KPI shows aggregate only | 3 or 4 — no breakdown field, or the filter flag is off |
| KPI shows every host in the data | 4 — `is_service_entity_filter=False`, so no filter is injected |

## The four layers

| # | Layer | Object | Required settings |
|---|---|---|---|
| 1 | Entity import | `itsi_entities` row | `title`, `identifier.fields`, `identifier.values`, `informational.*` |
| 2 | Service entity rules | `service.entity_rules` | One **alias**-type clause + one **info**-type clause, `rule_condition: AND` |
| 3 | KPI base search | `kpi_base_search` | `is_entity_breakdown`, `entity_breakdown_id_fields`, `entity_id_fields`, `entity_alias_filtering_fields` |
| 4 | Per-KPI flag | `kpi.is_service_entity_filter` | `true` — per-KPI, default `False` |

What each layer actually decides:

| Layer | Decides |
|---|---|
| 1 | Which alias exists at all. The alias used downstream **must** be in `identifier.fields`, and its value **must** equal what the metric stream produces for the Layer 3 breakdown field |
| 2 | *Which* entities bind (the info clause) and *which alias keys them* (the alias clause). Both required — the alias clause is the keystone that makes the Layer 4 mechanism wirable |
| 3 | Whether a filter clause *can* be injected. `entity_alias_filtering_fields` enables it |
| 4 | Whether it *is* injected. Layer 3 alone is not enough |

Layer 4 via REST PATCH works. Earlier "the API drops the bool" reports were validation
failures elsewhere in the payload (typically wiping `search`); a clean PATCH persists `True`.

## Failure modes mapped to layers

| Symptom in Service Analyzer | Layer | Check |
|---|---|---|
| Service has **0 entities** | 2, info clause | `info.<field>` value vs `_itsi_informational_lookups` on real entities. ITSI lowercases on import — match lowercase |
| **Wrong entities**, too many or too few | 1 or 2 | Do the entities carry the expected `info.<field>` value? Yes → rule value wrong. No → import wrong |
| Right entities, **aggregate only** | 3 | `is_entity_breakdown=false`, or `entity_breakdown_id_fields` names a column the base search does not output |
| Right entities, per-entity shown, **values bleed in from outside** | 4 | `is_service_entity_filter=False`. Toggle via UI or REST |
| Worked before, **now aggregate only** | 2 | The `<alias> matches *` clause was removed. Without it the filter has no key and silently falls back to aggregate |
| **Pseudo entities** (`unknown_host`, hash-suffixed) | 1 | `identifier.values` must match what `by host.name` produces |
| Only **`SHKPI-*` rows** in `itsi_summary`, zero KPI rows | 1/2 membership unresolved | The indicator derives `serviceid` via `match_entities(<alias>, sec_grp)` then `mvexpand`. Null `serviceid` drops every KPI row. Confirm `services > 0` on the entity, re-save the base search, wait for the next scheduled run |

## Worked example — OS Hosts via SIM

### Layer 1, entity import output

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
    "application::integrationbus"
  ]
}
```

| Detail | Why |
|---|---|
| `ITSIUniqueId` is in `identifier.fields` | Required for it to act as an alias-type rule field |
| `service::` value is lowercase | ITSI lowercases info-field values at import |
| `ITSIUniqueId` equals the clean host name | No hash suffix |

### Layer 2, service entity rule

```json
{
  "entity_rules": [{
    "rule_condition": "AND",
    "rule_items": [
      { "field": "ITSIUniqueId", "field_type": "alias", "rule_type": "matches", "value": "*" },
      { "field": "service",      "field_type": "info",  "rule_type": "matches", "value": "middleware-bus - platform" }
    ]
  }]
}
```

The `service` value is lowercased to match the import. The GUI displays mixed case; the stored
and rule values are lowercase.

GUI equivalents: **Service Split Field(s)** = `ITSIUniqueId`; **Service matches entities on
fields** = `service, ITSIUniqueId`; **Data filtered by service entities in field** =
`ITSIUniqueId`.

### Layer 3, generic base search

Reusable across deployments, nothing site-specific.

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

```json
{
  "is_entity_breakdown":           true,
  "entity_breakdown_id_fields":    "ITSIUniqueId",
  "entity_id_fields":              "ITSIUniqueId",
  "entity_alias_filtering_fields": "ITSIUniqueId",
  "metric_qualifier":              "",
  "metrics": [
    { "_key": "m_cpu",   "title": "CPU Utilization", "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_cpu_utilization", "unit": "%"  },
    { "_key": "m_mem",   "title": "Memory Free",     "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_memory_free_mb",  "unit": "MB" },
    { "_key": "m_diskr", "title": "Disk Read IOps",  "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_disk_read",       "unit": ""   },
    { "_key": "m_diskw", "title": "Disk Write IOps", "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_disk_write",      "unit": ""   },
    { "_key": "m_netrx", "title": "Network Rx",      "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_network_receive", "unit": ""   },
    { "_key": "m_nettx", "title": "Network Tx",      "aggregate_statop": "avg", "entity_statop": "avg", "threshold_field": "sa_network_send",    "unit": ""   }
  ]
}
```

### Layer 4, the KPI

```json
{
  "_key": "<uuid>",
  "title": "CPU Utilization",
  "search_type": "shared_base",
  "base_search_id":             "<base_search _key>",
  "base_search_metric":         "m_cpu",
  "is_entity_breakdown":        true,
  "entity_breakdown_id_fields": "ITSIUniqueId",
  "entity_id_fields":           "ITSIUniqueId",
  "is_service_entity_filter":   true,
  "threshold_field":            "sa_cpu_utilization",
  "unit":                       "%"
}
```

The KPI inherits base search settings, but `is_service_entity_filter` is a per-KPI override
defaulting to `False`. Set it explicitly.

## Worked example — flow model: N leaf lanes + 1 E2E rollup, one base search

The reusable idiom for modelling a flow (integration interfaces, process steps, pipeline
stages) as several leaf services plus an end-to-end rollup, while staying performance-minimal:
**one** base search and **one** indicator feed all of them, regardless of lane count.

| Component | Entity rule | Scope |
|---|---|---|
| Each leaf service | `iface matches "<lane>"` (alias) | That one lane's entity, because `is_service_entity_filter=True` |
| E2E rollup service | `flow_model matches "flow"` (info) | Every lane entity carrying the tag. No hard-coded list — tag a new interface and it joins automatically |

One real entity per lane, carrying `iface=<lane>` as identifier/alias and `flow_model=flow`
as an info tag. Each therefore belongs to **two** services, which is the fast
membership-resolution check:

```bash
GET /servicesNS/nobody/SA-ITOA/itoa_interface/entity?fields=title,iface,flow_model,services&count=0
# each lane entity -> services == 2 (leaf + rollup). 0 or 1 means membership is not resolved yet
```

### Why you get "only SHKPI rows, no KPI rows"

The generated indicator ends with the standard scoping block:

```spl
... | stats latest(...) AS alert_value_* by iface
| eval serviceid=null() | eval sec_grp="default_itsi_security_group"
| `match_entities(iface, sec_grp)`      <-- fills serviceid from ENTITY->SERVICE membership
| mvexpand serviceid                    <-- null serviceid means the row is DROPPED here
| appendpipe [ ... service_aggregate ... ]
| `assess_severity(<BS>)` | eval itsi_kpi_id=kpiid, itsi_service_id=serviceid
```

`serviceid` comes only from `match_entities`. Dispatch before ITSI resolves membership and
every lane row is dropped, leaving only the health monitor's `SHKPI-*` rows. It self-heals
once membership resolves. To force it: re-save the base search as a full-object POST to
regenerate the indicator, then wait for the next **scheduled** run — manual dispatch of ITSI
indicators is unreliable, see `splunk-itsi-kpi-creation-via-api`.

### Diagnose by service id, not by source

`itsi_summary` rows are keyed by `itsi_service_id` / `itsi_kpi_id`, not by a `source`
containing the base-search name. `source="*BS_Middleware_Flow*"` returns 0.

```spl
index=itsi_summary itsi_service_id IN ("<leaf1>","<leaf2>",...,"<e2e>") earliest=-30m latest=now
| stats latest(alert_value) AS v latest(alert_severity) AS sev count by itsi_service_id, itsi_kpi_id
```

Healthy: each leaf shows its own lane; the rollup shows sums or worst-of across lanes; a graded
KPI on one lane rolls its severity into the rollup's health.

Keep the base search on a sane `alert_period` — 30 min for a 24 h-window flow model — so it
does not add concurrency pressure. Do not create a base search per lane; that is the N×M
anti-pattern below.

## Debugging checklist

Walk the layers in order. Never reverse — each depends on the previous.

| # | Check | Query | Failure points to |
|---|---|---|---|
| 1 | Is the entity bound? Count > 0 | `GET .../itoa_interface/service/<key>?fields=entity_keys` | Layer 2 |
| 2 | Does the entity carry the alias in `identifier.fields`? | `GET .../itoa_interface/entity/<entity_key>` | Layer 1 — fix the import search |
| 3 | Does it have the expected info field at the expected value? | Same response, `_itsi_informational_lookups` for `service::<value>` | Layer 1 or 2 — compare both |
| 4 | Base search: breakdown true, and all three id-field settings on the same alias? | Inspect `kpi_base_search` | Layer 3 |
| 5 | Run the base search standalone. Does it output the alias column, with values matching step 2? | Splunk Search UI | Layer 1, or a wrong `rename` in Layer 3 |
| 6 | KPI: `search_type=shared_base`, correct `base_search_id`, `is_service_entity_filter=True`, id fields matching Layer 3? | Inspect the KPI | Layer 4 — PATCH or toggle |
| 7 | Force a re-run to pick up the new config | Open the service, click a KPI, Save with no change. Or `POST /services/saved/searches/<name>/dispatch` | — |

## Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Missing the alias-type `matches *` clause | Entities bind, KPI shows aggregate only | Add `{field: "<alias>", field_type: "alias", rule_type: "matches", value: "*"}` as the first rule item. It tells ITSI which alias to join on |
| `entity_alias_filtering_fields` set, per-KPI flag forgotten | KPI shows all hosts | Set `is_service_entity_filter=True` on each KPI. The base search setting alone does nothing |
| Base search renames to an alias the entity does not have | Base search returns rows, KPI shows zero entities | The `rename ... as <alias>` target must exist in `identifier.fields` |
| Rule value in mixed case | Looks unmatched in GUI testing, works in storage | Matching is case-insensitive for info fields; stored values are lowercased. Use lowercase |
| PATCH payload wipes `search` | 200 OK, but the flag does not change | Validation failure rolls back silently. Include the existing `search`, or omit the field |
| PATCH `is_service_entity_filter=False` where the rule has an alias clause | Stays `True` | ITSI re-asserts it. Working as designed |
| Same host in two services with different KPI sets | Both show the host | Fine, provided both rules match and both KPIs have the filter flag. Each KPI is scoped to its own service's entities |
| Units like `ops/s` or `B/s` | Blank in the UI | ITSI allows a controlled list (`%`, `MB`, `GB`, `ms`, `s`...). Others are silently blanked. Cosmetic |

## REST to GUI label mapping

| REST field | GUI label |
|---|---|
| `rule_items` with `field_type=alias, value=*` | Service Split Field(s) |
| `rule_items` with `field_type=info` | "Include entities matching...", one per row |
| `entity_alias_filtering_fields` on the base search | Data filtered by service entities in field |
| `is_service_entity_filter` on the KPI | "Filter to entities assigned to this service" checkbox |
| `entity_id_fields` from rules + KPI | Service matches entities on fields (read-only) |

If "Service matches entities on fields" shows only the info field and not the alias, Layer 2 is
missing its alias clause.

## Anti-patterns

| Anti-pattern | Why it hurts | Instead |
|---|---|---|
| Using an `info` field for filtering instead of an alias field | Info fields are for grouping, not high-cardinality join keys. Filter injection requires an alias-type field | Alias-type identifier (`ITSIUniqueId`, `host`, `aws_instance_id`) for filtering; info fields for business attributes |
| One base search per service | N services × M metrics searches all running the same `mstats`. Wastes the search head and scheduler | One generic base search per data source and entity type. All services share it; Layer 4 scopes each |
| Hard-coding the entity list with `where host IN (...)` | Does not track entity changes; bypasses the entity store | Entity store + rules + `is_service_entity_filter`, injected at search time |
| Breakdown true on the base search, false on the KPI | Silent aggregate-only; hours of debugging | Keep both consistent |
| Different alias fields across KPIs in one service | Each KPI joins differently; some work | One alias per service per entity type, used in the rule, base search and every KPI |
| Editing an entity to fix binding | The next import overwrites it | Fix the import search and re-run. The entity store is derived data |
| All four layers right, no thresholds | Per-entity rows populate, health stays gray (`alert_level=-1`) | Add `aggregate_thresholds` and `entity_thresholds`. See `splunk-itsi-kpi-creation-via-api` |
| **Graded** `entity_thresholds` on a high-cardinality or pseudo-entity KPI | Episode Review flood, below | Keep `entity_thresholds` flat until you deliberately want Event Analytics |

## Pseudo-entity thresholding and the Episode Review flood

Split-by pseudo-entities (`is_entity_breakdown=true`, `is_service_entity_filter=false`, no
entity-store objects) give per-item metrics without entity housekeeping. Graded entity
thresholds on them are a sharp edge.

**Mechanism.** The always-on correlation search `Service Monitoring - Entity Degraded` emits a
notable for every entity whose KPI severity is not `normal`, real or pseudo. Observed: ~1000
stuck-invoice pseudo-entities produced 4177 notables and 1067 episodes.

**Confirm it:**

```spl
index=itsi_grouped_alerts | search *<SERVICE_KEY>* | stats count by search_name
# "Service Monitoring - Entity Degraded" with a count close to the non-normal pseudo-entity count
```

**Keep it silent** while validating the pattern:

| Option | Effect |
|---|---|
| Flat `entity_thresholds`: `{"baseSeverityLabel":"normal","baseSeverityValue":2,"metricField":"<threshold_field>","thresholdLevels":[]}` | Everything computes `normal`, so `Entity Degraded` never matches. Per-entity values still populate — you keep the breakdown, you just do not grade it |
| Service under maintenance | Severities without notables, for the window |
| A count KPI with `is_entity_breakdown=false` | No per-entity severities to degrade. Pair with a separate breakdown KPI |

**Cleanup after a flood.** Get group ids from `index=itsi_grouped_alerts | search *<SERVICE_KEY>*
| stats count by itsi_group_id`, then close each:

```
POST /servicesNS/nobody/SA-ITOA/event_management_interface/notable_event_group/<id>?is_partial_data=1
{"status":"5"}
```

`itsi_grouped_alerts` keeps the status as at index time, so verify the close against the KV
store (`GET .../notable_event_group/<id>` → `status`), not the index.

## Related skills

| Skill | For |
|---|---|
| `splunk-stack-access-mcp-vs-api`, `splunk-itsi-api-access` | REST connectivity and tokens; ITSI capabilities and endpoints (prerequisite) |
| `splunk-itsi-entity-cmdb-lookup` | How the upstream CMDB CSV drives the info fields via the import |
| `splunk-itsi-kpi-creation-via-api` | KPI payload shapes, PATCH pitfalls, default health-score thresholds |
| `splunk-itsi-service-tree-design` | Where binding fits in the overall service tree |
| `splunk-itsi-flow-monitoring` | The flow model above, applied to bottleneck detection and step-latency trending |
