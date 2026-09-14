---
name: splunk-itsi-event-driven-service-health
category: itsi
description: >-
  Get meaningful ITSI service health in days by deferring Service Insights and driving health
  from events already being collected. Vendor-neutral and topology-neutral. Build the service
  tree from a CMDB, a spreadsheet, or the alert stream itself, group alerts into episodes with a
  NEAP, then bridge episodes to health with one episode-count KPI scoped per service through
  entity binding rather than hardcoded service names. Covers where the topology comes from, the
  two-layer no-hardcoding model, the shared base search and its entity-filter metadata, the adhoc
  fallback, SHKPI parent rollups, thresholds, alert normalization by field variable, REST deploy
  gotchas, and the SPL to prove health actually moved. Use when a new ITSI deployment needs value
  before any metric KPI exists, when alerts from any monitoring tool should drive service health,
  when building a service tree from a configuration source, or when episodes group correctly but
  service health stays stubbornly green.
disable-model-invocation: true
---

# Event-driven service health in ITSI

The fastest route to a useful ITSI deployment is to **defer Service Insights and start with Event
Analytics**. Alerts already arriving from any monitoring tool carry both a problem and the
identity of the thing that has it. That is enough to stand up a service tree and make it move.

Nothing here is tied to a vendor, a product, or a content pack, and the tree does not have to be
geographic. It is *topological* in the loosest sense: whatever hierarchy your alerts can be
attributed to — sites, applications, tenants, circuits, clusters, business units.

**Validated on:** ITSI 5.0 / Splunk 10.2.x on a lab instance (2026-09).

## Why start here

| | Event-driven start | Metric KPIs first |
|---|---|---|
| Input needed | alerts already landing in Splunk | metric data onboarded and modelled per KPI |
| KPIs per service | one | one per measured signal |
| First health score | same day | after onboarding, base searches and thresholds |
| What it tells you | something is wrong here, and what it affects | how a signal is trending |
| Earns its keep for | proving the service model, correlation, early value | capacity, SLOs, trend and prediction |

These are not alternatives. Event-driven health puts a correct service tree in front of people
early, when the argument is still about whether the model is right. Metric KPIs get added later,
per service, where they pay for themselves — and the tree does not change when they arrive.

## Where the topology comes from

The service tree is a **map that events attach to**. Any source of that map works, and the third
option below means you are never blocked waiting for a system of record.

| Source | How it lands in ITSI | Use when |
|---|---|---|
| Configuration management — CMDB, asset database, inventory API | export to CSV, import as entities, generate services from the same list | a system of record exists and is trusted |
| Manual — a spreadsheet somebody maintains | the same CSV path | the tree is small, or you are proving the idea |
| **The alert stream itself** | discover the distinct identifiers in the alerts, then create entities and services from that list | there is no system of record, or you want a tree today |

Deriving the tree from the events is the underrated one. The alerts already name the thing that
is broken, so the set of distinct identifiers *is* the leaf list:

```spl
index=<alert_index>
| stats count, dc(sourcetype) as sources, latest(_time) as last_seen by <candidate_field>
| sort -count
```

Run that for each field that might carry identity. The one you want has a stable, bounded set of
values and decent coverage across sources. Reject a field with thousands of values or a long tail
of one-offs — that is an event attribute, not a topology node.

Whatever the source, the output is the same, and it should be built programmatically so it can be
rebuilt: entities in `itsi_entities`, services in `itsi_services`, and entity rules on each
service binding the two. See `splunk-itsi-entity-cmdb-lookup` for the import itself.

```
┌─────────────────────┐     programmatic import      ┌──────────────────────────┐
│ Source of the map   │  ─────────────────────────►  │ ITSI KV (canonical map)  │
│ (CMDB / lookup /    │   entity import, REST, CP    │  • itsi_services         │
│  the alerts)        │                              │  • itsi_entities         │
└─────────────────────┘                              │  • entity_rules on svcs  │
         │                                           └────────────┬─────────────┘
         │  alert field aligns with entity alias / info           │
         ▼                                                        ▼
┌─────────────────────┐                              ┌──────────────────────────┐
│ Data Integration    │  identity field mapped       │ Episode KPI + entity     │
│ (variable mapping)  │  at connection time          │ filter (one definition)  │
└─────────────────────┘                              └──────────────────────────┘
```

The target is **one service template, one episode KPI, one normalization template**. Scale to N
services by importing the map, not by editing SPL per leaf.

## The three layers

| Layer | What happens |
|---|---|
| Event Analytics | alerts from any source become notable events; a NEAP groups them by the topology key |
| KPI bridge | one KPI counts open episodes per service from `itsi_grouped_alerts_index` |
| Service health | KPI severity → `service_health_monitor` → Service Analyzer |

**The bridge is the part people miss.** Associating episodes with a service does not change its
health score — nothing in Event Analytics moves health on its own. The episode-count KPI is the
explicit connection. Without it the tree stays green while episodes pile up underneath it, which
is the single most common reason this pattern appears not to work.

## Prerequisites

1. Alerts from one or more sources arriving in Splunk, ideally through **Data Integrations**, so
   the identity field is mapped at connection time rather than patched in SPL.
2. A **NEAP** grouping those notables by the topology key.
3. Services whose titles and/or bound entities carry the same key values.

## Avoiding hardcoded service names — two layers

| Layer | Mechanism | Hardcode-free? |
|---|---|---|
| **KPI scoping** (per-service episode count) | **entity linking** — `is_service_entity_filter: true` plus bound entities | yes, and it is the only generic option |
| **Alert normalization** (the notable's key field) | data integration field mapping with `{source_field}` variables | yes, mapped per connection |

**There is no SPL token variable** — no `$service$`, no `$node$` — in KPI searches. ITSI's
per-service KPI variable is `generate_entity_filter`, compiled per `(service_id, kpi_id)`.

A hardcoded `subcomponent="unit-02"` is a legitimate shortcut for a first proof, and the only
option when entities are absent. It costs an SPL edit per leaf forever after, so replace it with
entity linking before the tree grows.

## Two filtering modes

| Mode | When | Per-service scoping |
|---|---|---|
| **Entity-scoped** | the service has bound entities | ITSI injects `generate_entity_filter`; no hardcoded names |
| **Adhoc** | first proof, entity-less parents, or the alert key does not match any entity identifier | `\| search subcomponent="unit-02"` per service |

## Entity-scoped base search

Align the episode field with the **entity identifier** on the bound entities. Below, entities
expose the alias `topology_key` and episodes carry the same values in `subcomponent`. Substitute
whatever your topology actually keys on.

**Shared `kpi_base_search` — one definition for every service:**

```spl
`itsi_grouped_alerts_index` sourcetype="itsi_notable:group"
| join itsi_group_id
    [| inputlookup itsi_notable_group_system_lookup
    | eval itsi_group_id=_key
    | where is_active=1
    | fields itsi_group_id]
| eval topology_key=subcomponent
| stats count as episode_count by topology_key
```

**Base search metadata:**

| Field | Value |
|-------|-------|
| `entity_filter_field` | `topology_key` |
| `entity_split_field` | `topology_key` |
| `entity_alias_filtering_fields` | `topology_key` |
| `is_filter_entities_to_service` | `true` |
| `is_split_by_entity` | `false` (aggregate per service) or `true` (per-entity breakdown) |

**KPI — one definition in a service template, many services:**

| Field | Value |
|-------|-------|
| `search_type` | `shared_base` |
| `is_service_entity_filter` | `true` (JSON boolean, not `"0"`) |
| `entity_id_fields` | `topology_key` |
| `entity_breakdown_id_fields` | `topology_key` (if split) |
| `threshold_field` | `episode_count` |

ITSI then generates per-service indicator SPL containing:

```spl
| search [
    | rest splunk_server=local report_as=text
      service_id=<THIS_SERVICE>
      kpi_id=<THIS_KPI>
      entity_id_fields=topology_key
      entity_alias_filtering_fields=topology_key
      search_type=adhoc
      "/servicesNS/nobody/SA-ITOA/itoa_interface/generate_entity_filter"
    | return $value
]
```

That subsearch expands to the `topology_key` values of the entities bound to *this* service — no
manual filter per leaf.

### Service entity rules

Both clauses are needed (see `splunk-itsi-entity-binding-architecture`):

```json
"entity_rules": [{
  "rule_condition": "AND",
  "rule_items": [
    { "field": "topology_key", "field_type": "alias", "rule_type": "matches", "value": "*" },
    { "field": "<your_selector>", "field_type": "info", "rule_type": "matches", "value": "<scopes entities to this service>" }
  ]
}]
```

The alias clause makes the filter resolvable; the info clause is what narrows it to one service.
Verify entities are actually bound before enabling `is_service_entity_filter`, or the generated
filter matches nothing and the KPI reads zero forever.

### Parent services

| Approach | Generic? |
|----------|----------|
| **SHKPI rollup only** — parent has no episode KPI, depends on its children's `SHKPI-*` | yes, and no entity binding needed |
| **Entity filter on parent** — bind every descendant entity to the parent too | yes; one episode KPI, filter covers all bound keys |
| **Hardcoded `subcomponent IN (...)`** | no — first-proof shortcut only |

Prefer the SHKPI rollup unless you have a reason to bind descendants to the parent.

```json
"services_depends_on": [
  {"serviceid": "<child-uuid>", "kpis_depending_on": ["SHKPI-<child-uuid>"]}
]
```

## Adhoc fallback

```spl
`itsi_grouped_alerts_index` sourcetype="itsi_notable:group"
| join itsi_group_id
    [| inputlookup itsi_notable_group_system_lookup
    | eval itsi_group_id=_key
    | where is_active=1
    | fields itsi_group_id]
| search subcomponent="unit-02"
| stats count as episode_count
```

Set `is_service_entity_filter: false`.

## Thresholds

| `episode_count` | Severity | Notes |
|-----------------|----------|-------|
| 0 | Normal (2) | `gap_custom_alert_value: 0`, base severity normal |
| ≥ 1 | Critical (6) | `thresholdLevels` with `thresholdOperator: >=`, `thresholdValue: 1` |

Set **`importance: 11`** if an open episode should dominate the service's health score.

## A tree with no metric KPIs

**Leaves:** `ServiceHealthScore` plus the episode KPI. That is the whole configuration.

**Parents:** no KPI at all — health follows the worst child through `services_depends_on` on the
child `SHKPI-*`. A parent with no KPIs is not a broken service; it is the normal shape for a
rollup.

This is what makes the pattern cheap. A hundred-leaf tree is one KPI definition, one base search,
one set of entity rules, and an import.

## REST deploy notes

### Template-linked services

Services created from a service template stay linked to it, and cloning a KPI from one carries
linkage fields that a POST will reject. To add a custom KPI:

1. Clone an existing KPI from the service.
2. **Strip** `base_service_template_id`, `kpi_template_kpi_id`, `service_id`, `_rev`.
3. Set `search_type: adhoc` (or `shared_base`) and replace the `search*` fields.
4. `POST .../service/{id}?is_partial_data=1` with `{"kpis": [<new_kpi_only>]}`.

Leaving the linkage fields in returns a 400. Prefer forking the template, or the service-unlink
pattern in `splunk-itsi-kpi-creation-via-api`, over editing a shipped template in place.

### `is_service_entity_filter`

Use the JSON boolean `false`, **not** the string `"0"` — which is truthy in ITSI validation and
fails with `SI-SRVC-CFG_0001`.

### Verify

```spl
# Episodes exist and carry the key
index=itsi_grouped_alerts sourcetype=itsi_notable:group
| stats count by subcomponent

# The KPI wrote to summary
index=itsi_summary itsi_kpi_id=<episode-kpi-uuid>
| sort -_time | head 5
| table _time alert_value alert_level alert_severity

# Health actually propagated
index=itsi_summary source=service_health_monitor itsi_service_id=<service-uuid>
| sort -_time | head 3
| table _time health_score severity_label
```

Work down that list in order. Each stage failing has a different cause, and the third is the one
that tells you the bridge is wired.

Dispatch the indicator once after deploy rather than waiting for the schedule:

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "trigger_actions=1" \
  "$ITSI_URL/servicesNS/nobody/itsi/saved/searches/Indicator%20-%20<KPI_UUID>%20-%20ITSI%20Search/dispatch"
```

## Deploy script

Drive the whole thing from one script that reads `ITSI_TOKEN` and `ITSI_URL` from the
environment, clones a KPI off an existing service, strips the linkage fields above, and POSTs it
back per service. Keep the script in the project repo next to the content pack rather than in the
skill, so the service list stays with the environment it describes.

```bash
export ITSI_TOKEN='<rest-token>'
export ITSI_URL='https://<stack>:8089'
python3 deploy_episode_kpi.py
```

## Alert normalization

Map the identity field **at connection time**, not in SPL, so one template serves every source.
A coalesce chain over the candidate field names keeps the template free of source-specific logic:

```text
{subcomponent} → {node} → {site_name} → {location} → {service_name} → {region} → "-"
```

At connection setup, pick the field your source actually sends, or add an `eval` in the ingestion
search. The resulting values must match your service titles and/or the entity alias.

**Entity association** is configured per connection, not in the template stanza — point
`association.entity_lookup_field` at whichever alias your entity type exposes.

Leave `service_ids` empty unless you deliberately want to pin alerts to specific services.

## Content pack outline

| Object | Purpose |
|--------|---------|
| `itsi_data_integration_template` | variable identity field plus mapping options |
| `kpi_base_search` | shared episode count; entity filter fields set to the topology key |
| Service template | one episode KPI (`shared_base`, `is_service_entity_filter: true`) plus entity rules with the alias clause |
| Service tree | parents roll up SHKPI only; leaves carry the episode KPI and the bound entities |

Ship it as your own overlay content pack rather than modifying one you did not write.

## Anti-patterns

- Expecting NEAP grouping or service association alone to move health. It will not.
- Adding the KPI to a template-linked service without stripping the linkage fields.
- `is_service_entity_filter: "0"` as a string instead of the boolean `false`.
- Counting `itsi_tracked_alerts` instead of active episodes (`itsi_grouped_alerts` joined to the
  active-group lookup) — closed groups inflate the count and health never recovers.
- Choosing a high-cardinality field as the topology key because it looked descriptive.

## Does ITSI 5.0 change any of this?

No. The constraints are architectural, not a missing feature.

| Question | Answer |
|----------|--------|
| Still need entity linking to avoid hardcoded names? | **Yes.** `generate_entity_filter` is unchanged — it reads the service's bound entities from KV at KPI compile time. |
| Does ITSI already use KV internally? | **Yes.** Services, entities, data integration templates and episodes all live in KV collections. |
| Can I point KPIs at my own KV collection instead? | **No**, not through supported APIs. Entity rules and `generate_entity_filter` only understand ITSI entities with proper types, aliases and info fields. |
| So what is the supported programmatic route? | Populate the canonical objects: import entities, create services with entity rules, align the alert field through data integration variables. |
| 5.0 data-integration changes? | New event data model (`generic_v2`, `event_type`, `dedup_key`, `ci_*` enrichment). Template storage is still KV and field-mapping variables behave the same. |

**Bottom line:** KV is already the engine. You do not bypass entity linking with a sidecar
collection — you feed the right collections from whatever source your map comes from.

## Prior art

The **ThousandEyes content pack** ships this pattern already: an alert-count KPI that turns test
alerts into service health. It is the clearest shipped implementation to read before building
your own, and the origin of the approach described here.

Splunk's public [Network Event Intelligence workshop](https://splunk.github.io/observability-workshop/en/scenarios/network-event-intelligence/)
walks one concrete instance end to end — two alert sources, a site hierarchy, a custom NEAP — and
is a useful worked example provided you read the site hierarchy as one topology among many rather
than as the point.

## Related skills

- `splunk-itsi-entity-binding-architecture` — the four-layer chain behind `generate_entity_filter`
- `splunk-itsi-entity-cmdb-lookup` — lookup-driven entity import, whatever the source of the map
- `splunk-itsi-kpi-creation-via-api` — thresholds, silent rollback, indicator dispatch
- `splunk-itsi-service-tree-design` — SHKPI dependencies and repeatable tree builds
- `splunk-itsi-content-pack-creation` — shipping the map, template and KPI together
- `splunk-itsi-api-access` — REST stays on the management port 8089 even where the UI is on 443
