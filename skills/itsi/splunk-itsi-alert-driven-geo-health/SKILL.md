---
name: splunk-itsi-alert-driven-geo-health
category: itsi
description: Generic ITSI pattern for making a service tree come alive from external alerts, not only geographic ones. Import services and entities once (lookup, entity import, REST, or content pack) as a repeatable programmatic map for events, then drive health from a single episode-count KPI. Health comes from Data Integrations plus NEAP plus alert KPIs, never metric KPIs. Per-service scoping needs entity binding (`generate_entity_filter`, `is_service_entity_filter`); alert normalization uses data-integration field variables. Covers the two-layer no-hardcoding model, entity-scoped versus adhoc KPI filtering, SHKPI parent rollups, REST deploy gotchas, ITSI 5.0 KV-store wiring, and validation SPL. Use when building alert-driven service health, lookup or CMDB-backed service trees, entity-linked KPI filtering, or ThousandEyes-style alert bridges on any hierarchy — sites, apps, perimeters, business units.
disable-model-invocation: true
---

# ITSI Alert-Driven Service Health

Generic pattern for making **any service tree "come alive" from external alerts** — with the minimum work to get started. Import services + entities once (lookup, entity import, REST, or content pack) to build a **repeatable programmatic map** that events can attach to. Health is driven by alert KPIs, not metric KPIs.

**A geographic site hierarchy** is the reference implementation used throughout — the same wiring applies to app perimeters, business units, stores, data centers, or any other tree where alerts carry an identifier that can align with imported entities.

**Validated on:** ITSI 5.0 / Splunk 10.2.x on a lab instance (2026-09).

## Bootstrap map (generic)

```
┌─────────────────────┐     programmatic import      ┌──────────────────────────┐
│ Source of truth     │  ─────────────────────────►  │ ITSI KV (canonical map)  │
│ (lookup / CMDB /    │   entity import, REST, CP    │  • itsi_services         │
│  vendor API / CSV)  │                              │  • itsi_entities         │
└─────────────────────┘                              │  • entity_rules on svcs  │
         │                                           └────────────┬─────────────┘
         │  alert field aligns with entity alias / info            │
         ▼                                                        ▼
┌─────────────────────┐                              ┌──────────────────────────┐
│ Data Integration    │  subcomponent / entity       │ Episode KPI + entity     │
│ (variable mapping)  │  lookup field                │ filter (one definition)  │
└─────────────────────┘                              └──────────────────────────┘
```

Goal: **one service template + one episode KPI + one normalization template** — scale to N services by importing the map, not by hand-editing SPL per leaf.

See also `splunk-itsi-entity-cmdb-lookup` for lookup-driven entity import that feeds the map.

## Concept

| Layer | What drives health |
|-------|-------------------|
| Event Analytics | Catalyst + SolarWinds → notable events → NEAP groups by `subcomponent` (site) |
| KPI bridge | `Active Network Episodes` counts open episodes per site from `itsi_grouped_alerts_index` |
| Service health | KPI severity → `service_health_monitor` → Service Analyzer tile |

Episodes linked via `subcomponent` **do not** change health by themselves. This KPI is the explicit bridge (same idea as ThousandEyes `RoutingAlertCount`).

## Prerequisites

1. **Data Integrations** for Catalyst Center and SolarWinds with `subcomponent = itsi_site` (or `vendor_region`).
2. **NEAP** grouping on `subcomponent` (e.g. "Network Events by Location").
3. **Geo services** in ITSI — site names must match episode `subcomponent` values (`NY HQ`, `Store-101`, `Store-102`).

## Avoiding hardcoded service names — two layers

| Layer | Mechanism | Hardcode-free? |
|-------|-----------|----------------|
| **KPI scoping** (per-service episode count) | **Entity linking only** — `is_service_entity_filter: true` + bound entities | Yes — the only generic approach |
| **Alert normalization** (notable `subcomponent`) | Data integration field mapping with `{source_field}` variables | Yes — map vendor field at connection time |

**There is no SPL token variable** (like `$site$`) in KPI searches. ITSI's per-service KPI "variable" is **`generate_entity_filter`**, compiled per `(service_id, kpi_id)`. Hardcoded `subcomponent="Store-102"` in KPI SPL is a lab shortcut; it is the **only** alternative when entities are absent.

A hardcoded filter is a deliberate shortcut for a first proof. Replace it with entity linking before the tree grows, or every new site becomes another SPL edit.

## Two KPI filtering modes

| Mode | When to use | Per-service scoping |
|------|-------------|---------------------|
| **Entity-scoped (production)** | Service has bound entities (Catalyst Sites, hosts, tests…) | ITSI injects `generate_entity_filter` — no hardcoded site names |
| **Adhoc / hardcoded (first proof)** | Quick proof, entity-less parents, or `subcomponent` ≠ entity ID | `| search subcomponent="Store-102"` per service |

## Entity-scoped base search (generic / content-pack default)

Align the episode join field with the **entity identifier** used on bound entities. For the Enterprise Networking CP, site entities expose alias `site_name`; episodes here use `subcomponent` with the same values (`NY HQ`, `Store-101`, …).

**Shared `kpi_base_search` (one definition, all site services):**

```spl
`itsi_grouped_alerts_index` sourcetype="itsi_notable:group"
| join itsi_group_id
    [| inputlookup itsi_notable_group_system_lookup
    | eval itsi_group_id=_key
    | where is_active=1
    | fields itsi_group_id]
| eval site_name=subcomponent
| stats count as episode_count by site_name
```

**Base search metadata:**

| Field | Value |
|-------|-------|
| `entity_filter_field` | `site_name` |
| `entity_split_field` | `site_name` |
| `entity_alias_filtering_fields` | `site_name` |
| `is_filter_entities_to_service` | `true` |
| `is_split_by_entity` | `false` (aggregate count per service) or `true` (per-site entity breakdown) |

**KPI (in service template — one KPI, many services):**

| Field | Value |
|-------|-------|
| `search_type` | `shared_base` |
| `is_service_entity_filter` | `true` (JSON boolean, not `"0"`) |
| `entity_id_fields` | `site_name` |
| `entity_breakdown_id_fields` | `site_name` (if split) |
| `threshold_field` | `episode_count` |

ITSI then generates per-service indicator SPL containing:

```spl
| search [
    | rest splunk_server=local report_as=text
      service_id=<THIS_SERVICE>
      kpi_id=<THIS_KPI>
      entity_id_fields=site_name
      entity_alias_filtering_fields=site_name
      search_type=adhoc
      "/servicesNS/nobody/SA-ITOA/itoa_interface/generate_entity_filter"
    | return $value
]
```

That subsearch expands to the **site_name values of entities bound to this service** — no manual `subcomponent="..."` per leaf.

### Service entity rules (required for entity filter)

Both clauses are needed (see `splunk-itsi-entity-binding-architecture`):

```json
"entity_rules": [{
  "rule_condition": "AND",
  "rule_items": [
    { "field": "site_name", "field_type": "alias", "rule_type": "matches", "value": "*" },
    { "field": "<your_selector>", "field_type": "info", "rule_type": "matches", "value": "<scopes entities to this service>" }
  ]
}]
```

The Catalyst site template in that content pack uses `cisco_catalyst_host` / `site_hierarchy` info rules instead — verify entities are actually bound before enabling `is_service_entity_filter`.

### Parent geo services (CA, NY, US)

| Approach | Generic? |
|----------|----------|
| **SHKPI rollup only** — parent has no episode KPI, depends on child `SHKPI-*` | Yes — no entity binding needed on parent |
| **Entity filter on parent** — bind all child-site entities to parent (e.g. info `region=CA`) | Yes — one episode KPI, filter includes all bound `site_name` values |
| **Hardcoded `subcomponent IN (...)`** | No — lab shortcut only |

Prefer **SHKPI rollup** for parents unless you explicitly bind site entities to the parent service.

## Adhoc KPI search (lab / fallback)

```spl
`itsi_grouped_alerts_index` sourcetype="itsi_notable:group"
| join itsi_group_id
    [| inputlookup itsi_notable_group_system_lookup
    | eval itsi_group_id=_key
    | where is_active=1
    | fields itsi_group_id]
| search subcomponent="Store-102"
| stats count as episode_count
```

Set `is_service_entity_filter: false`. Use when entities are absent or `subcomponent` ≠ entity identifier.

## Thresholds

| `episode_count` | Severity | Notes |
|-----------------|----------|-------|
| 0 | Normal (2) | `gap_custom_alert_value: 0`, base severity normal |
| ≥ 1 | Critical (6) | `thresholdLevels` with `thresholdOperator: >=`, `thresholdValue: 1` |

Set **`importance: 11`** on this KPI if it should dominate service health when episodes are open.

## Geo tree without metric KPIs

**Leaf services:** only `ServiceHealthScore` + `Active Network Episodes`.

**Parent services (CA, NY, US):** no metric KPIs — either:
- **Option A:** episode KPI with regional `subcomponent IN (...)` filter, or
- **Option B:** rollup only via `services_depends_on` → child `SHKPI-*` (health follows worst child).

```json
"services_depends_on": [
  {"serviceid": "<child-uuid>", "kpis_depending_on": ["SHKPI-<child-uuid>"]}
]
```

## REST deploy notes

### Template-linked services

Site services created from the `DA-ITSI-CP-enterprise-networking` service template stay linked to it. To add a **custom** KPI:

1. Clone an existing KPI from the service.
2. **Strip** before POST: `base_service_template_id`, `kpi_template_kpi_id`, `service_id`, `_rev`.
3. Set `search_type: adhoc`, replace all `search*` fields with episode SPL.
4. `POST .../service/{id}?is_partial_data=1` with `{"kpis": [<new_kpi_only>]}`.

Do **not** clone template linkage fields — ITSI returns 400.

### `is_service_entity_filter`

Use JSON boolean `false`, **not** string `"0"` (truthy in ITSI validation → `SI-SRVC-CFG_0001`).

### Verify

```spl
# Episode count by site
index=itsi_grouped_alerts sourcetype=itsi_notable:group
| stats count by subcomponent

# KPI wrote to summary
index=itsi_summary itsi_kpi_id=<episode-kpi-uuid>
| sort -_time | head 5
| table _time alert_value alert_level alert_severity

# Health propagated
index=itsi_summary source=service_health_monitor itsi_service_id=<service-uuid>
| sort -_time | head 3
| table _time health_score severity_label
```

Dispatch indicator once after deploy:

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "trigger_actions=1" \
  "$ITSI_URL/servicesNS/nobody/itsi/saved/searches/Indicator%20-%20<KPI_UUID>%20-%20ITSI%20Search/dispatch"
```

## Deploy script

Drive the whole thing from one script that reads `ITSI_TOKEN` and `ITSI_URL` from the
environment, clones a KPI off an existing service, strips the template-linkage fields listed
below, and POSTs it back per service. Keep the script in the project repo next to the content
pack rather than in the skill, so the service list stays with the environment it describes.

**Deployed on a lab instance (2026-09):** `Active Network Episodes` KPI added to:
- Store-102, Store-101, NY HQ (sites)
- CA, NY, United States (geo rollups)

Base search object: `network-active-episodes-by-site`.

## Generic alert normalization template

Shipped in `DA-ITSI-CP-network-alert-health` (`network_alert_geo` data source). No hardcoded site or service names — only source-field variables.

**`subcomponent` (service / NEAP link)** — coalesce chain, first match wins:

```text
{subcomponent} → {itsi_site} → {site_name} → {Location} → {service_name} → {vendor_region} → "-"
```

At connection setup, pick which source field your vendor actually sends (or add an `eval` in the ingestion SPL). Values must match ITSI **service titles** and/or entity alias `site_name`.

**Entity association** (configured per connection, not in the template stanza):

| Goal | Set `association.entity_lookup_field` to |
|------|------------------------------------------|
| Site entities (Enterprise Networking CP) | `site_name` or `SiteNameHierarchy` |
| Host / device entities | `src`, `DeviceName`, or `itsi_entity_id` |
| ThousandEyes-style tests | entity alias field from your entity type |

Leave `service_ids` empty unless you want to pin alerts to specific services.

**Deploying the template:**

```bash
export ITSI_TOKEN='<rest-token>'
export ITSI_URL='https://<stack>:8089'
python3 deploy_network_alert_geo_template.py
```

Verify: `GET .../event_management_interface/data_integrations/template/network_alert_geo`

## Content pack outline

| Object | Purpose |
|--------|---------|
| `itsi_data_integration_template` | `network_alert_geo` — variable subcomponent + mapping_field_options for entity/service fields |
| `kpi_base_search` | Shared episode count; `eval site_name=subcomponent`; entity filter fields = `site_name` |
| Service template | One `Active Network Episodes` KPI (`shared_base`, `is_service_entity_filter: true`) + entity rules with alias clause |
| Service tree | US → CA/NY → sites; **parents rollup SHKPI only**; leaves get episode KPI + site entities |

Ship as overlay CP `DA-ITSI-CP-network-alert-health` — do not edit the shipped enterprise-networking template in place; add KPI via template fork or service-unlink pattern from `splunk-itsi-kpi-creation-via-api`.

## Anti-patterns

- Expecting NEAP/service association alone to move health — it will not.
- Adding episode KPI to template-linked service without stripping `base_service_template_id`.
- Using `is_service_entity_filter: "0"` (string) instead of `false`.
- Counting `itsi_tracked_alerts` instead of **active episodes** (`itsi_grouped_alerts` + active lookup join) — inflates counts with closed groups.

## ITSI 5.0 — same limitations? KV store?

**Yes — the wiring is the same in ITSI 5.0.** The constraints are architectural, not a missing feature you can work around with a custom KV collection.

| Question | Answer |
|----------|--------|
| Does ITSI 5.0 still require entity linking to avoid hardcoded service names in KPIs? | **Yes.** `generate_entity_filter` is unchanged — it reads bound entities for the service from KV at KPI compile time. |
| Does ITSI already use KV internally? | **Yes.** Services (`itsi_services`), entities (`itsi_entities`), data integration templates (`itsi_data_integration_template`), episodes, and most ITSI config live in KV collections. |
| Can I put my own "map" in a custom KV collection and point KPIs at it? | **No** — not through supported ITSI APIs. `generate_entity_filter` and service entity rules only understand **ITSI entities** with proper types, aliases, and info fields. |
| What is the supported way to build the map programmatically? | Populate canonical KV objects: **(1)** import entities (lookup → entity import, REST `POST .../entity`, or CP), **(2)** create services + entity rules (REST or CP), **(3)** align alert fields via data integration variables. |
| ITSI 5.0 data-integration changes? | New event data model (`generic_v2`, `event_type`, `dedup_key`, `ci_*` CMDB enrichment). Template storage is still KV; field-mapping variables work the same. Upgrade path exists per connection. |
| Lookup as map source? | **Yes** — CSV lookup → entity import → `itsi_entities` KV. This is the repeatable pattern for non-vendor-native hierarchies (see `splunk-itsi-entity-cmdb-lookup`). |

**Bottom line:** KV is already the engine — you don't bypass entity linking with a sidecar KV; you **feed the right KV collections** (`itsi_entities` + service entity rules) from your lookup or API in a repeatable deploy script or content pack.

## Related skills

- `splunk-itsi-entity-binding-architecture` — 4-layer chain for `generate_entity_filter`
- `splunk-itsi-entity-cmdb-lookup` — lookup-driven entity import as programmatic map
- `splunk-itsi-kpi-creation-via-api` — thresholds, silent rollback, indicator dispatch
- `splunk-itsi-service-tree-design` — SHKPI dependencies, sandbox naming, repeatable tree build
- `splunk-itsi-content-pack-creation` — ship map + template + KPI as CP
- `splunk-itsi-api-access` — REST stays on the management port **8089** even where the UI is on 443

## Related external skills

Getting the alerts flowing in the first place is a separate job from modelling their health.
For onboarding the Cisco network sources this pattern consumes, see
[`chambear2809/splunk-cisco-skills`](https://github.com/chambear2809/splunk-cisco-skills):
`cisco-enterprise-networking-setup` and `cisco-catalyst-ta-setup` cover the app, TA, and data
onboarding layer, and hand off ITSI content design to skills like this one.
