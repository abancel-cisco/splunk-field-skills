---
name: splunk-itsi-content-pack-creation
category: itsi
description: >-
  End-to-end playbook for authoring a custom Splunk ITSI Content Pack (CP) from scratch — a deployable .tar.gz Splunk app produced by the ITSI "Create Content Pack" wizard that bundles services, KPIs, kpi_base_searches, service templates, and dashboards into a reusable artifact (e.g. for DB monitoring, business transactions, or a customer-specific overlay). Covers the five phases (1. design the CP scope; 2. build the components in ITSI via REST in leaves-first order; 3. verify entity binding + KPI data + dependencies BEFORE packaging; 4. run the wizard click-by-click with the exact field values; 5. install + cleanup redundant predecessor objects on the target env), the pre-flight checklist that prevents the two most expensive silent failures (Bug 4 case-sensitivity on entity rules, the kpi_base_search `is_metric` trap), the difference between authoring services in-tree (so the wizard picks them up automatically) vs. drafting standalone templates, the wizard's "select a service, get the dependency closure for free" behavior, the install-side pitfalls (sec_grp / Global team membership for cross-team consumption, app-load order vs SIM content pack, sourcetype-vs-index conflicts), the post-deploy cleanup pattern of disabling the predecessor base searches the new consolidated CP replaces, AND the in-place consolidation alternative path (when you don't want to ship a CP at all but instead repoint existing KPIs from per-metric SIM base searches onto your consolidated one and disable the predecessors directly — covers the four hidden-state landmines that ITSI does NOT auto-reconcile when you PATCH a KPI's `base_search_id`: stale `entity_alias_filtering_fields` causing zero entity matches, stale `target_field` pointing at the OLD column name, stale `aggregate_thresholds.metricField` / `entity_thresholds.metricField` inherited from a CPU-template clone, stale field references buried inside `time_variate_thresholds_specification` JSON; plus the search-head-load false-negative pattern where itsi_summary probes return zero rows during the very performance crunch you're trying to fix, the backing-saved-search disable mechanism in the `itsi` app namespace, ITSI's auto-cleanup of orphaned backing saved searches, and the tablespace-style cardinality exception that prevents full consolidation). Use when authoring a brand-new ITSI content pack from scratch, when extending the topology under an existing service (e.g. Application Performance Monitoring → Database → Database Oracle), when consolidating multiple per-metric base searches into one shared base search before packaging, when preparing to run the ITSI "Create Content Pack" wizard, when guiding a step-by-step packaging session, when planning the post-install cleanup of obsolete predecessor objects, when repointing existing KPIs onto a different base_search_id without packaging a CP, when disabling redundant kpi_base_search objects without deleting them, when reducing search head load by eliminating redundant scheduled searches, or when the user mentions ITSI content pack creation / CP wizard / Create Content Pack / DA-ITSI-CP-* app authoring / content pack export / "just replace the base searches" / KPI repointing / kpi_base_search disable / search head performance / skipped searches cleanup.
disable-model-invocation: true
---

# ITSI Content Pack Creation — End-to-End Playbook

How to design, build, verify, package, and deploy a custom Splunk ITSI Content Pack (CP). Tested on a real project (Oracle DB monitoring CP that consolidated 6 redundant SIM base searches into one).

## When to use this skill

- Authoring a brand-new ITSI Content Pack from scratch (DB monitoring, business transactions, customer-specific overlay)
- Extending the topology under an existing service from a shipped CP (e.g. SIM CP's `Application Performance Monitoring`)
- Consolidating multiple per-metric base searches into a single shared one before packaging
- Preparing to run the ITSI **Create Content Pack** wizard
- Walking a colleague through the wizard click-by-click
- Planning the post-install cleanup of obsolete predecessor objects (e.g. disable 6 SIM base searches the new CP replaces)
- **In-place consolidation without packaging a CP** — repointing existing KPIs onto a consolidated base search and disabling the predecessors directly (the "we're late, skip the CP, just replace the base searches" path — see Phase 5b)
- Reducing search head load by disabling redundant `kpi_base_search` backing saved searches
- The user mentions "ITSI content pack creation", "CP wizard", "Create Content Pack", "DA-ITSI-CP-*", "content pack export", "just replace the base searches", "KPI repointing", "kpi_base_search disable", "skipped searches"

Prerequisites:
- REST access already working — see `splunk-itsi-api-access`
- Service tree design conventions understood — see `splunk-itsi-service-tree-design`
- KPI / kpi_base_search authoring understood — see `splunk-itsi-kpi-creation-via-api`
- The two silent killers below (entity-rule case sensitivity, the `is_metric` trap) read at least once

## What an ITSI Content Pack actually is

The **Create Content Pack** wizard packages a *closure of ITSI KV-store objects* into a standard Splunk app (`.tar.gz`) that any other ITSI instance can install. The closure is rooted at one or more **services you select**, and the wizard automatically pulls in their:

- Direct child services (via `services_depending_on_me`)
- KPIs (because they live inside the service object)
- kpi_base_searches referenced by those KPIs
- Service templates the services are linked to
- Threshold templates referenced by the KPIs
- Optionally: glass tables, deep dives, neaps, notable event aggregation policies that reference any of the above

**Key insight**: the wizard is *not* a builder. It only packages objects that **already exist** in your ITSI. So you must build the services + KPIs + base searches *in your live ITSI first*, verify them, and only then run the wizard.

This is the opposite of the older "write conf files by hand" approach that often surfaces in old documentation. The modern (ITSI 4.13+) flow is: build via UI/REST → verify → wizard packages → export → install elsewhere.

## The five-phase flow

```
┌────────────────────────────────────────────────────────────────┐
│ Phase 1: DESIGN the CP scope and topology (1-2 hr)             │
│   - One CP per logical domain (DB monitoring, biz txns, etc.)  │
│   - Decide leaf services vs. service template                  │
│   - Decide where leaves attach to the existing tree            │
│   - Decide which predecessor objects this CP will replace      │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ Phase 2: BUILD components in ITSI via REST (1-3 hr)            │
│   - Leaves-first: base searches → leaves → rollups → patch APM │
│   - Apply the pre-flight checklist (Bug 4, is_metric trap)     │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ Phase 3: VERIFY before packaging (30 min)                      │
│   - Entity binding count > 0 on each leaf                      │
│   - KPI data flowing (Service Analyzer shows colored tiles)    │
│   - Base search produces all KPI-target columns                │
│   - Service Analyzer topology matches design                   │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ Phase 4: RUN the Content Pack wizard (15 min)                  │
│   - User clicks; assistant dictates exact field values         │
│   - Select root service(s); review the auto-pulled closure     │
│   - Download the .tar.gz                                       │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ Phase 5: INSTALL + CLEANUP on the target env (30 min)          │
│   - Install the .tar.gz as a Splunk app                        │
│   - Verify topology lands intact                               │
│   - Disable predecessor objects (the 6 SIM base searches etc.) │
│   - Document version + tested date in BUG_FIXES.md             │
└────────────────────────────────────────────────────────────────┘
```

## Pre-flight checklist (the two silent killers)

Before you build anything, internalize these two failure modes. Both produce *zero error logs*, *200 OK on every API call*, and *empty KPIs* — they will eat hours if you don't know them.

### Killer 1: Entity rule case sensitivity

ITSI's `info`-type entity-rule clauses are case-sensitive. If you write:

```json
{ "field": "entity_type", "field_type": "info", "rule_type": "matches", "value": "os hosts" }
```

…the service binds zero entities, because the entity store has `entity_type = "OS Hosts"` (verbatim case). Every KPI is then silent. **Always query the entity store first** to get the canonical value:

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/entity?fields=entity_type&count=200" \
  | python3 -c "
import sys, json
items = json.load(sys.stdin)
items = items if isinstance(items, list) else items.get('entry', [])
seen = set()
for e in items:
    for et in (e.get('entity_type') or []):
        seen.add(et if isinstance(et, str) else et.get('value', ''))
print(sorted(seen))
"
```

This is the single most common reason a service shows zero bound entities, and it is
worth checking before any deeper debugging.

### Killer 2: kpi_base_search `is_metric` trap

If your consolidated `base_search` SPL contains *anything* beyond a bare `| mstats ... where ... by ... span=...` (any `eval`, `rename`, `dedup`, `where`, derived ratio, etc.) AND you set `is_metric: true`, the metric optimizer silently rejects the search. KPIs show no data even though running the SPL in oneshot returns rows perfectly.

**Rule of thumb**: default to `is_metric: false` (Ad hoc Search) for any consolidated base search with derived metrics or column renames. Full diagnosis in `splunk-itsi-kpi-creation-via-api` → "Authoring a kpi_base_search — the `is_metric` trap".

### Companion fields to align on every custom base search

| Field | Recommended value | Why |
|---|---|---|
| `is_metric` | `false` (Ad hoc Search) | Avoid the trap above |
| `is_service_entity_filter` | `true` | Allows per-KPI `is_service_entity_filter: true` to actually filter |
| `entity_alias_filtering_fields` | `"ITSIUniqueId"` (or your alias) | Tells ITSI which column is the join key |
| `source_itsi_da` | `""` (empty string) | Non-empty values lock the search in the UI |
| `sec_grp` | `"default_itsi_security_group"` (Global) | Required for cross-team consumption when packaged in a CP |

## Phase 1 — Design the CP scope and topology

### Pick the right scope (one CP per logical domain)

✅ DO: one CP per coherent domain. Examples that make sense as a single CP:
- "Database monitoring" (Oracle + Postgres + SQL Server)
- "Business transaction monitoring" (order-to-cash, invoice processing)
- "Customer-specific overlay" (Customer-Platform + Customer-CMDB)

❌ DON'T: bundle unrelated things ("all my custom stuff") into one CP. Smaller, focused CPs are easier to install selectively, version independently, and maintain.

### Service vs. service template — which to ship?

| Ship a... | When | What you select in the wizard |
|---|---|---|
| **Live service** | The CP provides ready-to-use monitoring for a specific deployment (e.g. "Database Oracle" with the consolidated base search) | The service. The wizard pulls KPIs + base search automatically |
| **Service template** | The CP provides a blueprint that customers instantiate themselves (e.g. "Fulfilment-Orders-* - Platform" — one per perimeter) | The template. New services created from it inherit the KPI set |
| **Both** | The CP provides both a starter service AND a template for similar instances | Select both; wizard packages each separately |

For DB monitoring: ship a live service per engine (`Database Oracle`, `Database Postgres`), each pre-wired to its consolidated base search. Customers select the service in the wizard CP install flow and get monitoring immediately. No template needed if there's only one DB instance per engine type per customer.

### Where do leaves attach in the tree?

If the SIM CP is installed and you want to extend its `Application Performance Monitoring` service, the topology becomes:

```
Application Performance Monitoring  (SIM CP — DO NOT MODIFY)
 ├── Database                                       (your new rollup — Global team)
 │    ├── Database Oracle                          (your leaf — 13 Oracle KPIs)
 │    └── Database Postgres                        (your leaf — N Postgres KPIs)
 └── ...other SIM CP children...
```

**Critical**: extend the SIM service via `is_partial_data=1` PATCH (append to `services_depending_on_me`), never via full POST. Full POST clobbers the rest of the SIM service. See `splunk-itsi-service-tree-design` for the safe-build pattern.

### Decide which predecessor objects this CP replaces

If your CP consolidates 6 per-metric SIM base searches into one, list them upfront so Phase 5 cleanup is mechanical:

```
Predecessors to disable after CP install:
  - "Oracle DB - CPU Time" base search
  - "Oracle DB - Sessions" base search
  - "Oracle DB - Hard Parses" base search
  - "Oracle DB - SQL Executions" base search
  - "Oracle DB - Logical Reads" base search
  - "Oracle DB - Physical Reads" base search
```

Save this list — Phase 5 needs it.

## Phase 2 — Build the components in ITSI via REST

### Order matters: leaves-first, dependencies-second

```
1. Create the consolidated kpi_base_search          (no deps)
2. Create the leaf service(s) with their KPIs       (depend on base search)
3. Create the rollup service(s)                     (depend on leaves)
4. Patch the parent service to include the rollup   (is_partial_data=1)
```

The leaves-first order means single-pass: every reference is resolvable when made. See `splunk-itsi-service-tree-design` for why this matters at scale.

### Consolidated kpi_base_search — the right shape

```json
{
  "title":                          "DBM Oracle Database (Consolidated)",
  "description":                    "Single consolidated base search for all Oracle DB KPIs",
  "search_type":                    "shared_base",
  "search_alert_earliest":          "0",
  "earliest_time_offset":           "0",
  "is_entity_breakdown":            true,
  "entity_breakdown_id_fields":     "ITSIUniqueId",
  "entity_alias_filtering_fields":  "ITSIUniqueId",
  "is_service_entity_filter":       true,
  "is_metric":                      false,
  "metric_qualifier":               "",
  "source_itsi_da":                 "",
  "sec_grp":                        "default_itsi_security_group",
  "alert_period":                   "5",
  "alert_lag":                      "60",
  "base_search":                    "| mstats latest(\"oracledb.cpu_time\") as ora_cpu_time, latest(\"oracledb.parse_calls\") as ora_parses ... | eval ora_hard_parse_ratio_pct = ... | dedup _time ITSIUniqueId oracledb.instance.name",
  "metrics": [
    { "_key": "m_cpu_time",         "title": "Oracle CPU Time",         "threshold_field": "ora_cpu_time",  "unit": "s",  "aggregate_statop": "avg", "entity_statop": "avg", "gap_severity": "info", "fill_gaps": "null_value" },
    { "_key": "m_sessions",         "title": "Oracle Sessions",         "threshold_field": "ora_sessions",  "unit": "",   "aggregate_statop": "avg", "entity_statop": "avg", "gap_severity": "info", "fill_gaps": "null_value" }
    // ... one entry per KPI target column ...
  ]
}
```

POST to `/servicesNS/nobody/SA-ITOA/itoa_interface/kpi_base_search`. Save the returned `_key` — you'll need it for KPI payloads.

### Leaf service with KPIs

Two approaches:
1. **Clone a canary KPI** (best — gets you all 80+ fields right): GET a working KPI from a SIM service (e.g. `Oracle Sessions Used %`), `copy.deepcopy()`, modify `_key` / `title` / `base_search_metric` / `threshold_field` / `unit`, append to your service's `kpis` array.
2. **Build from scratch**: only when no canary is available. Risk: easy to miss a required field; ITSI silently rejects the whole `kpis` array.

Either way, see `splunk-itsi-kpi-creation-via-api` for the read-modify-write pattern and the silent-rollback trap.

Entity rule on the leaf service:

```json
{
  "entity_rules": [{
    "rule_condition": "AND",
    "rule_items": [
      { "field": "ITSIUniqueId", "field_type": "alias", "rule_type": "matches", "value": "*" },
      { "field": "entity_type",  "field_type": "info",  "rule_type": "matches", "value": "OS Hosts" }
    ]
  }]
}
```

Note: `OS Hosts` (capitalized). If your CP scopes to a database-instance-level entity instead of host-level, use the appropriate entity_type — but always verify the canonical case first.

### Patching the existing parent service (non-destructive append)

```python
import copy

# GET the existing parent (e.g. SIM CP's Application Performance Monitoring)
apm = http('GET', f"/servicesNS/nobody/SA-ITOA/itoa_interface/service/{APM_KEY}")

existing_deps = apm.get('services_depends_on') or []
new_dep = {
    "serviceid":    DATABASE_ROLLUP_KEY,
    "kpis_depending_on": [f"SHKPI-{DATABASE_ROLLUP_KEY}"]
}

# Only append if not already present
if not any(d.get('serviceid') == DATABASE_ROLLUP_KEY for d in existing_deps):
    new_deps = existing_deps + [new_dep]
    http('POST',
         f"/servicesNS/nobody/SA-ITOA/itoa_interface/service/{APM_KEY}?is_partial_data=1",
         {"services_depends_on": new_deps})
```

`is_partial_data=1` is **mandatory** — without it, the POST replaces the entire APM service object, wiping the SIM CP's children. This is a one-way mistake; you'd have to reinstall the SIM CP to recover.

## Phase 3 — Verify before packaging

Each of these should pass before you touch the wizard. Failures here cost minutes; failures at the wizard step cost the entire packaging cycle.

### Check 1: Entity binding count > 0 on each leaf

```bash
SVC_KEY=<your leaf service _key>
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service/$SVC_KEY?fields=entities,entity_rules" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('entities:', len(d.get('entities') or []))"
```

If 0: Bug 4 (case sensitivity), missing alias clause (Bug 3), or no entities of that type exist yet.

### Check 2: Base search produces all KPI-target columns

```python
SPL = bs['base_search']
KPI_COLS = [m['threshold_field'] for m in bs.get('metrics', []) if m.get('threshold_field')]

# Run the SPL as oneshot
req = urllib.request.Request(
    f"{ITSI_URL}/services/search/jobs/oneshot",
    data=urllib.parse.urlencode({
        'search': SPL, 'output_mode': 'json',
        'earliest_time': '-30m', 'count': '5'
    }).encode(),
    headers={'Authorization': f'Bearer {TOKEN}'}, method='POST'
)
with urllib.request.urlopen(req, context=CTX) as r:
    results = json.loads(r.read()).get('results', [])

print(f"  oneshot rows: {len(results)}")
present_cols = set(results[0].keys()) if results else set()
missing = [c for c in KPI_COLS if c not in present_cols]
print(f"  KPI columns present: {len(KPI_COLS)-len(missing)}/{len(KPI_COLS)}")
if missing: print(f"  MISSING: {missing}")
```

If rows > 0 and all columns present, the base search is healthy. If rows > 0 but some columns missing, the SPL doesn't expose every column referenced by your KPIs — fix the SPL.

### Check 3: KPIs show data in Service Analyzer

UI: **ITSI → Service Analyzer → <your service>** → tiles should be coloured (green / amber / red), not gray.

If gray with "no data": base search isn't running (Killer 2 — `is_metric` trap), or KPI's `base_search_metric` references a non-existent metric `_key`.

### Check 4: Topology matches design

UI: **ITSI → Service Analyzer → topology view** — verify the hierarchy is what you designed (e.g. APM → Database → Database Oracle).

If the new rollup doesn't appear under the parent, the `is_partial_data=1` patch didn't take, or the dependency wiring used the wrong KPI key.

## Phase 4 — Run the Content Pack wizard

UI path: **ITSI → Configuration → Content Library → Create Content Pack** (button top-right).

### Wizard step 1 — General info

| Field | What to enter | Notes |
|---|---|---|
| **Content Pack Name** | Human-readable title (e.g. `Buttercup DB Monitoring`) | Becomes the title in the Content Library |
| **App ID** | App folder name (e.g. `DA-ITSI-CP-buttercup-dbm`) | Must start with `DA-ITSI-CP-` by convention. No spaces; kebab-case |
| **Version** | Semver (e.g. `1.0.0`) | Bump on every export |
| **Author** | Your name / team | Free text |
| **Description** | 2-3 sentences: what it provides, prerequisites | Customer-facing |
| **Icon** | Optional SVG | Skip on first export; add later |

### Wizard step 2 — Select services

Tick the **leaf service(s)** at the bottom of your new tree. The wizard automatically pulls:
- The leaf service object
- Its KPIs (they live inside the service)
- The `kpi_base_search` each KPI references
- Threshold templates referenced by the KPIs
- The chain of `services_depends_on` *up* to the highest parent the wizard can see

**Don't select the SIM CP's parent service** (e.g. `Application Performance Monitoring`) — that pulls the entire SIM tree into your CP, which is what you want to *avoid*. Stop at the boundary of "your" content. Select only your leaves; the wizard handles parent linkage via metadata.

### Wizard step 3 — Select additional objects

Empirically (verified on ITSI 4.20+), the wizard's "additional objects" page exposes checkboxes only for these object classes:

- **Dashboards**
- **Macros**
- **Saved searches** (non-KPI scheduled searches)
- **Props** (props.conf — sourcetype definitions)
- **Transforms** (transforms.conf — regex extractions)
- **Lookups**

That's the entire opt-in surface. Tick only the ones your CP actually needs. For typical KV-store-only CPs (services + KPIs + base searches), **leave every box unticked** — everything that matters was already pulled by the Step-2 service selection.

### What the wizard does NOT package (the blind spot)

This is the corner case you'll hit on any non-trivial CP. The wizard's universe of packageable objects is bounded:

| Object class | How the wizard handles it |
|---|---|
| Services | Auto-packaged via Step-2 service selection |
| KPIs inline on services | Auto-packaged with the service |
| kpi_base_searches referenced by those KPIs | Auto-packaged (followed through KPI refs) |
| Threshold templates referenced by KPIs | Auto-packaged |
| Service templates linked to selected services | Auto-packaged |
| Auto-generated SHKPIs (one per service) | Auto-packaged |
| Dashboards / Macros / Saved searches / Props / Transforms / Lookups | Opt-in via Step-3 checkboxes |
| **Entity types** | **NOT offered by the wizard** |
| **Glass tables** | **Not offered in many ITSI versions** (some builds allow it) |
| **Deep dives** | Not offered |
| **Notable event aggregation policies** | Not offered |
| Modular alert actions, custom commands, scripts, custom data models | Not offered |

If your CP needs *anything* in the bottom four rows, the wizard will silently produce an *incomplete* package. The install will succeed but the dependent functionality (e.g. an entity type your service's entity rule references, a glass table that visualizes your services) will be missing.

### Sidecar app pattern (when the blind spot bites)

Pattern when you need to ship objects outside the wizard's universe:

1. **Build a sidecar Splunk app** alongside the main CP. Naming convention:
   `DA-ITSI-CP-<your-cp>-extras` or `DA-ITSI-<your-cp>-overlay`
2. Put the leftover bits there as conf-format exports:
   - Entity types → `default/itsi_entity_type.conf`
   - Glass tables → use the ITSI Glass Table import format (XML/JSON depending on ITSI version)
   - Aggregation policies → `default/itsi_notable_event_*.conf`
   - Modular alert actions → `default/alert_actions.conf` + scripts in `bin/`
3. **Cross-link via `app.conf [dependencies]` stanza** so Splunk's app installer enforces install order. In the *sidecar's* `default/app.conf`:
   ```
   [dependencies]
   DA-ITSI-CP-splunk-observability-cloud-database-monitoring = required
   ```
   (i.e. "the main CP must be present"). And optionally in the *main CP's* description text, document the sidecar as a soft prerequisite.
4. Document in **both** READMEs that the apps are paired. Add to the wizard-side "Prerequisites" field of the main CP a line: *"and the companion sidecar app `DA-…-extras` (ships separately)"*.

### The SIM TA's `sim_modular_input` ("Splunk Infrastructure Monitoring Data Streams")

A category-specific case of the blind spot above. If your CP queries `sim_metrics` for any application-specific metric family (`oracledb.*`, `postgresql.*`, `kafka.*`, `redis.*`, custom OTel receivers, etc.), the metrics arrive in `sim_metrics` only because someone configured a `sim_modular_input` modular input in `splunk_ta_sim`. That input runs a SignalFlow program against O11y Cloud and ingests the resulting time series.

**What the SIM TA ships out of the box (verified 2026-06)**:

| Modular input type | `sim_modular_input` ("Splunk Infrastructure Monitoring Data Streams") |
| Shipped SAMPLE templates (disabled by default) | `SAMPLE_AWS_EC2`, `SAMPLE_AWS_Lambda`, `SAMPLE_Azure`, `SAMPLE_Containers`, `SAMPLE_GCP`, `SAMPLE_Kubernetes`, `SAMPLE_OS_Hosts` |
| **Shipped templates for databases** | **None.** No `SAMPLE_Oracle_DB`, no `SAMPLE_PostgreSQL`, etc. |
| **Shipped templates for application middleware** | **None.** No Kafka, Redis, RabbitMQ, etc. |

**Implication**: any CP that queries application-specific O11y metrics MUST also ship (or document) the SignalFlow program. Without it, the customer installs the CP, sees empty KPIs, has no idea what's missing.

### Where to put the SignalFlow program

Three options, in increasing order of automation:

| Option | Effort | What customer does on install | When to use |
|---|---|---|---|
| **(A) Document only** | Lowest | Manually copy-paste SignalFlow text into Splunk UI per program | Single-customer or single-instance; fast to ship |
| **(B) Sidecar TA app** with `inputs.conf` stanzas | Medium | Install the sidecar TA → modular inputs appear pre-configured | Multi-customer / production-ready |
| **(C) Bundled in the CP itself** | Not possible | n/a | The CP wizard does NOT package modular inputs; this option doesn't exist |

The pragmatic default for a fresh CP is **(A)**: place the SignalFlow text as plain-text files in a `signalflow_programs/` subfolder of the CP's distribution directory, with install steps in the README. The reference DBM CP does this for `oracle_db.signalflow` and `postgres_db.signalflow`.

### Extracting an existing SignalFlow program from a live ITSI

If a colleague has already configured a working modular input (e.g. the customer's own ops team set up `Oracle_DB`), extract the SignalFlow text via REST so you can ship it:

```bash
TOKEN=$ITSI_TOKEN; URL=$ITSI_URL
INPUT_NAME="Oracle_DB"

curl -sk -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/-/-/data/inputs/sim_modular_input/$INPUT_NAME?output_mode=json" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = d['entry'][0]['content']
print('# Pulled from sim_modular_input:', '$INPUT_NAME')
print('# index:', c.get('index'), '  interval:', c.get('interval'), 'sec')
print('# org_id:', c.get('org_id'))
print()
print(c.get('signal_flow_programs', ''))
" > "${INPUT_NAME}.signalflow"
```

The `signal_flow_programs` field is plain SignalFlow text. Splunk redacts nothing; you can ship it directly.

### Authoring a new SignalFlow program

Pattern (per metric, one line each, separated by `;`):

```
data('<metric.name>').promote('<dim1>',['<dim2>',...,]allow_missing=True).publish();
```

The `promote(...)` dimensions become Splunk fields on the resulting metric event. **Always include the host dimension** (`host.name` for OTel collectors, `host` for some legacy receivers) so the entity alias join works downstream. Include any other dimensions you'll want to break down by in KPI queries (e.g. `oracledb.instance.name`, `postgresql.database.name`, `tablespace_name`).

`allow_missing=True` tells SignalFlow not to fail the program if some metrics aren't yet flowing — useful when the receiver is being deployed gradually across hosts.

### Pre-wizard checklist: do you need a sidecar?

Run through this before opening the wizard. If the answer to any is "yes", you'll need a sidecar:

- Does any service in your CP reference a **custom entity type** (one not shipped by an installed dependency CP like SIM)?
- Do you have a **glass table** that visualizes your services and you want to ship it together?
- Do you have **deep dives** that the customer should get out of the box?
- Do you have **notable event aggregation policies** that bind to your KPIs?
- Do you have **modular alert actions** the customer will trigger from KPIs?
- Are you relying on **lookups, macros, props, or transforms** that don't exist on a typical target install? (these CAN be ticked in Step-3 — included in the main CP)

For pure KV-store-content CPs (services + KPIs + base searches + maybe service templates) the answer is "no sidecar needed" — most observability-driven CPs fall here.

### Wizard step 4 — Review and download

The wizard shows a summary table of what's being packaged. Verify the counts match expectations:
- N services (your leaves + rollups)
- M KPIs (= number-of-KPIs-per-leaf × number-of-leaves)
- K kpi_base_searches (typically 1 per leaf if you consolidated)
- Service templates: as expected

Click **Create Content Pack**. The wizard generates a `.tar.gz` file in your browser's download folder.

### What the .tar.gz contains

```
DA-ITSI-CP-buttercup-dbm.tar.gz
└── DA-ITSI-CP-buttercup-dbm/
    ├── default/
    │   ├── app.conf
    │   ├── itsi_service.conf            # your services as conf entries
    │   ├── itsi_kpi_template.conf       # your KPIs
    │   ├── itsi_kpi_base_search.conf    # your base searches
    │   ├── itsi_service_template.conf   # your templates (if any)
    │   └── savedsearches.conf           # the scheduled searches for each KPI
    ├── metadata/
    │   └── default.meta                 # global read access
    ├── appserver/
    │   └── static/                      # icon assets
    └── README.txt                       # auto-generated
```

This is a standard Splunk app folder. Install via Splunk's app-install flow (UI or CLI).

## Phase 5 — Install and clean up on the target environment

### Install the CP

UI: **Splunk Web → Apps → Manage Apps → Install app from file** → upload the `.tar.gz` → restart Splunk if prompted.

CLI:
```bash
splunk install app /path/to/DA-ITSI-CP-buttercup-dbm.tar.gz
splunk restart  # if prompted
```

### Post-install verification

1. **Service Analyzer**: your new tree appears under the expected parent
2. **Configuration → Services**: count of services matches what the wizard packaged
3. **Configuration → Base Searches**: your consolidated base search appears, `Last run` is recent
4. **KPI tiles colored** within ~5 min (one scheduling interval)

### Cleanup: disable the predecessor objects

This is the value the CP unlocks. With the consolidated base search now running, the 6 SIM per-metric base searches it replaces become redundant — they were causing the search head load the user wanted to reduce.

**Disable, don't delete.** Splunk Cloud doesn't allow deleting shipped saved searches. Disable means the scheduled search stops running; the conf entry stays so it's reactivatable if the rollback is needed.

```bash
TOKEN=$ITSI_TOKEN
URL=$ITSI_URL

# List the predecessor base searches to disable
PREDECESSORS=(
  "Oracle DB - CPU Time"
  "Oracle DB - Sessions"
  "Oracle DB - Hard Parses"
  "Oracle DB - SQL Executions"
  "Oracle DB - Logical Reads"
  "Oracle DB - Physical Reads"
)

for name in "${PREDECESSORS[@]}"; do
  encoded=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$name")
  curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
    "$URL/servicesNS/nobody/DA-ITSI-CP-splunk-observability/saved/searches/$encoded/disable"
  echo "Disabled: $name"
done
```

Wait one scheduling interval (~5 min) and confirm in **Settings → Searches, reports, and alerts**: the disabled searches show "Disabled" status; their `Last run` stops advancing.

### Sanity check after cleanup

The new consolidated base search should still be running, the KPIs should still be coloured. If KPIs go gray after disabling the predecessors, you disabled too many — the predecessor list contained one your new CP doesn't replace. Re-enable, audit your predecessor list, retry.

### Document for future you

In the content pack's source folder:
- `README.md` — what this CP does, prerequisites, install steps
- `BUG_FIXES.md` — which Splunk + ITSI + SIM CP versions you tested against, known issues
- `CHANGELOG.md` — versions of your CP and what changed in each

## Phase 5b — In-place consolidation without packaging a CP (the "just replace the base searches" path)

Real project scenario (2026-06): the consolidated base search was already built and live on the source env, the CP `.tar.gz` was downloaded, but the user said *"we're late, park the CP, just replace the base searches for our use cases"*. The goal was the same as Phase-5 cleanup — disable 6 redundant SIM per-metric base searches to relieve a search-head that was skipping searches — but without going through install-on-target. The KPIs on the existing services had to be **repointed** to the consolidated base search in place.

This alternative path is **substantially trickier than building from scratch**. The shipped wizard install flow handles 80+ KPI fields correctly because it serializes the whole object. Patching a KPI's `base_search_id` via REST touches only the field you set — and ITSI **does not auto-reconcile** the other fields that carry references to the old base search. Three iterative fix passes are typical before everything flows.

### When to use this path vs. proper CP install

| Use Phase 5b (in-place repoint) when... | Use Phase 5 (full CP install) when... |
|---|---|
| The consolidated base search already exists on the target env | You're shipping to a fresh ITSI |
| Time pressure: the customer needs perf relief NOW | You have time to validate the CP cycle |
| The cleanup is for one specific deployment, not a reusable artifact | The CP needs to be reusable across customers |
| The target env has heavy customization you don't want to overwrite | Greenfield deployment |
| You want zero risk of accidentally replacing existing services | You're confident the install won't conflict |

Phase 5b is a "surgical patch" path. Phase 5 is the "rebuild from package" path. Both end at the same place — old searches disabled, new consolidated one driving everything.

### Step-by-step procedure (4 phases, 4 fix passes, 1 verification window)

#### 1. Audit — list ALL base searches in scope and their consumers

Before touching anything, inventory which `kpi_base_search` objects pull the metric family you're consolidating, and for each one, which KPIs on which services depend on it. This is the kill-list candidate set. Categorize each as:

- **KEEP** — has consumers you want to preserve
- **KILL** — has consumers you're migrating, or zero consumers
- **INVESTIGATE** — has consumers in unfamiliar services (need human decision)

```python
# Cross-reference all *Oracle*-named kpi_base_searches against all services
all_bs = http('GET', "/servicesNS/nobody/SA-ITOA/itoa_interface/kpi_base_search?count=500&fields=_key,title,is_metric,base_search,source_itsi_da")
oracle_bs = [bs for bs in all_bs if 'oracle' in (bs.get('title','') + (bs.get('base_search') or '')).lower()]

services = http('GET', "/servicesNS/nobody/SA-ITOA/itoa_interface/service?count=500&fields=_key,title,kpis")
# Map base_search_key -> [(service_title, kpi_title, base_search_metric, threshold_field)]
consumers = {}
for svc in services:
    for k in (svc.get('kpis') or []):
        bs_id = k.get('base_search_id')
        if bs_id:
            consumers.setdefault(bs_id, []).append({
                'service': svc['title'],
                'kpi':     k.get('title'),
                'metric':  k.get('base_search_metric'),
                'tf':      k.get('threshold_field'),
            })

for bs in oracle_bs:
    cons = consumers.get(bs['_key'], [])
    print(f"{bs['title']!r}  consumers={len(cons)} on {len(set(c['service'] for c in cons))} services")
```

The output gives you the impact analysis. **Always present this to the user for per-service approval before repointing** — silently silencing KPIs on services they didn't know depended on the old base search is a deeply unpleasant surprise.

#### 2. Extend the consolidated base search to cover the column needs of ALL the KPIs you're about to repoint

Before repointing, map each old KPI's `threshold_field` to what column the consolidated will need to expose. Often the consolidated SPL **already pulls the raw metric** but doesn't expose the post-eval'd column in its `metrics[]` catalog — in that case, just add catalog entries (no SPL change needed). When the consolidated genuinely lacks a column (e.g. needed a unit conversion, or a different aggregation semantic like "cumulative deadlocks" vs "deadlocks/s rate"), extend the SPL minimally:

```python
# Read current
bs = http('GET', f"/servicesNS/nobody/SA-ITOA/itoa_interface/kpi_base_search/{BS_KEY}")
old_spl = bs['base_search']

# Minimal SPL additions: 1 extra mstats column + 1 extra eval
new_spl = old_spl.replace(
    'rate("oracledb.enqueue_deadlocks") as ora_enqueue_deadlocks_rate',
    'rate("oracledb.enqueue_deadlocks") as ora_enqueue_deadlocks_rate, '
    'latest("oracledb.enqueue_deadlocks") as ora_enqueue_deadlocks_total'
)
new_spl = new_spl.replace(
    ' | dedup _time ',
    ' | eval ora_pga_memory_mb = round(ora_pga_memory / 1048576, 2) | dedup _time '
)

# Append new catalog entries (clone an existing entry's structure as template)
template = next(m for m in bs['metrics'] if m['_key'] == 'ora_sessions_pct')
bs['base_search'] = new_spl
bs['metrics'] = bs['metrics'] + [
    {**template, '_key': 'ora_processes_pct',           'title': 'Processes Used %',          'unit': '%',         'threshold_field': 'ora_processes_pct'},
    {**template, '_key': 'ora_user_rollbacks_rate',     'title': 'User Rollbacks /s',         'unit': '/s',        'threshold_field': 'ora_user_rollbacks_rate'},
    {**template, '_key': 'ora_pga_memory_mb',           'title': 'PGA Memory (MB)',           'unit': 'MB',        'threshold_field': 'ora_pga_memory_mb'},
    {**template, '_key': 'ora_enqueue_deadlocks_total', 'title': 'Enqueue Deadlocks (cumul.)', 'unit': 'deadlocks', 'threshold_field': 'ora_enqueue_deadlocks_total'},
]
http('PUT', f"/servicesNS/nobody/SA-ITOA/itoa_interface/kpi_base_search/{BS_KEY}", bs)

# Verify the new columns are produced by running the SPL as oneshot — NOTE: do NOT prefix `search `
# (the SPL already starts with `| mstats`, which is a generating command)
res = oneshot(bs['base_search'], earliest='-15m')
new_cols = ['ora_processes_pct', 'ora_user_rollbacks_rate', 'ora_pga_memory_mb', 'ora_enqueue_deadlocks_total']
for c in new_cols:
    sample = (res['results'][0] if res['results'] else {}).get(c)
    print(f"  {c}: sample={sample}")
```

**Important corner cases**:
- **Unit conversions** (bytes → MB, total → rate, cumulative counter → derivative): add as a new column rather than reusing/mutating the existing one. Old KPI thresholds were calibrated to the old unit; preserving the unit semantic preserves the thresholds without recalibration.
- **Different aggregation semantics** (e.g. consolidated has `rate(deadlocks)` but old KPI was `latest(deadlocks)`): add both. The two are not interchangeable for thresholds — `rate` resets per cycle, `latest` is monotonic since process start. Customers tuning thresholds for one will hate the surprise of the other.
- **Cardinality blockers** (e.g. tablespace metrics that need per-tablespace breakdown): these inherently can't fold into a single-row base search. Keep them on their own dedicated base search. Don't try to be clever — multi-row dimensions explode every other column's cardinality. See the **Tablespace exception** below.

#### 3. Repoint each KPI's three minimum-required fields

```python
REPOINT_MAP = {
    # old_threshold_field: (new_base_search_metric, new_threshold_field)
    'sessions_pct':     ('ora_sessions_pct',            'ora_sessions_pct'),
    'procs_pct':        ('ora_processes_pct',           'ora_processes_pct'),
    'commit_rate':      ('ora_user_commits_rate',       'ora_user_commits_rate'),
    'rollback_rate':    ('ora_user_rollbacks_rate',     'ora_user_rollbacks_rate'),
    'cache_hit_pct':    ('ora_cache_hit_ratio_pct',     'ora_cache_hit_ratio_pct'),
    'pga_mb':           ('ora_pga_memory_mb',           'ora_pga_memory_mb'),
    'deadlocks_total':  ('ora_enqueue_deadlocks_total', 'ora_enqueue_deadlocks_total'),
    # ... one row per old threshold_field
}

for svc_title in ['AppA-Oracle-DB - Platform', 'AppB-Oracle-DB - Platform']:
    svc = http('GET', f".../service?filter={url(json({{'title': svc_title}}))}&fields=_key")
    svc = http('GET', f".../service/{svc[0]['_key']}")
    for k in svc.get('kpis') or []:
        if (k.get('_key') or '').startswith('SHKPI-'): continue
        tf = k.get('threshold_field')
        if tf not in REPOINT_MAP: continue
        new_metric, new_tf = REPOINT_MAP[tf]
        k['base_search_id']     = NEW_BS_KEY
        k['base_search_metric'] = new_metric
        k['threshold_field']    = new_tf
    http('PUT', f".../service/{svc['_key']}", svc)
```

This is the minimum repoint. It will appear to work at first glance (`PUT` returns 200), but **most KPIs will silently produce no data**. Continue to pass 4.

#### 4. Cleanup the four hidden-state fields ITSI does NOT auto-reconcile

This is the heart of Phase 5b — the part that wasted hours when I first did it. After changing `base_search_id` on a KPI, four other fields commonly carry stale state pointing at the OLD base search or the original CPU-template clone heritage. ITSI does not reconcile them on PUT.

| Stale field | Symptom when wrong | Fix |
|---|---|---|
| `entity_alias_filtering_fields` (string, e.g. `"ITSIUniqueId"`) | `null` on repointed KPI → ITSI can't filter base search rows to entities → **zero events emitted** for this KPI | Set to the new base search's `entity_alias_filtering_fields` value (typically `"ITSIUniqueId"`) |
| `target_field` (string) | Points at the OLD column name (e.g. `"cache_hit_pct"`); ITSI tries to find that column in the new base search output → fails → **no events emitted** | Clear to `None` (KPI uses `threshold_field` instead) OR set to the new column name |
| `metric` (dict, `{"metric_index": "...", "metric_name": "..."}`) | Heritage value like `{"metric_name": "cpu.utilization"}` from when the KPI was originally cloned from a CPU template; harmless in many cases but pollutes diagnostics | Clear to `{"metric_index": "", "metric_name": ""}` |
| `aggregate_thresholds.metricField` and `entity_thresholds.metricField` | Values like `"sa_cpu_utilization"` or `"shared_base"` from the CPU-template clone heritage; ITSI looks up `metricField` to threshold against and may compute N/A | Set both to a sensible value matching the working pattern on a known-good KPI (e.g. `"count"`), or leave unchanged if KPI is already firing |
| Embedded references inside `time_variate_thresholds_specification` JSON | The threshold policy JSON can contain old column names buried in `policies > default_policy > aggregate_thresholds.metricField` or similar — invisible without a deep walk | Recursively `deep_replace_strings` the JSON, mapping each old column → new column |

The fix script (proven on a 2026-06 project):

```python
COLUMN_RENAME = {
    'sessions_pct':   'ora_sessions_pct',
    'cache_hit_pct':  'ora_cache_hit_ratio_pct',
    'pga_mb':         'ora_pga_memory_mb',
    # ... one row per old → new column rename
}
def deep_replace(obj, m):
    if isinstance(obj, dict):  return {k: deep_replace(v, m) for k, v in obj.items()}
    if isinstance(obj, list):  return [deep_replace(v, m) for v in obj]
    if isinstance(obj, str) and obj in m: return m[obj]
    return obj

for svc in [ORDERS_SVC, MIDDLEWARE_SVC]:
    for k in svc.get('kpis') or []:
        if k.get('base_search_id') != NEW_BS_KEY: continue  # only the repointed ones

        # Fix 1: entity_alias_filtering_fields
        k['entity_alias_filtering_fields'] = 'ITSIUniqueId'

        # Fix 2: target_field (if pointing at an old column)
        if k.get('target_field') in COLUMN_RENAME:
            k['target_field'] = None

        # Fix 3: metric heritage
        k['metric'] = {'metric_index': '', 'metric_name': ''}

        # Fix 4: deep-walk threshold blocks + tvs JSON
        for fname in ('aggregate_thresholds', 'entity_thresholds', 'time_variate_thresholds_specification'):
            if k.get(fname):
                k[fname] = deep_replace(k[fname], COLUMN_RENAME)
    http('PUT', f".../service/{svc['_key']}", svc)
```

Expect to discover **more stale fields per iteration** — diff a working KPI against a failing one on the same service, look at every field that differs, and pattern-match. Each cleanup pass typically unblocks 30-60% of remaining KPIs. Three passes is normal; five is not unreasonable on heavily customized KPIs.

#### 5. Verify — and beware the search-head-load false-negative trap

Wait one base-search scheduling interval (typically 5 min), then probe `itsi_summary` to confirm each repointed KPI is emitting events with non-N/A values.

```python
spl = ('search index=itsi_summary earliest=-10m '
       '| stats latest(_time) as last_t, latest(alert_value) as v, latest(alert_severity) as sev '
       'by kpi, kpiid')
```

**Critical caveat — the false-negative trap**: Phase 5b is usually run BECAUSE the search head is overloaded (skipped searches). That same overload **delays the consolidated base search's runs**, so your `itsi_summary` probe may legitimately return zero rows for a KPI that's perfectly configured — the search just hasn't been scheduled to run yet, or its result hasn't indexed. **Don't iterate "fixes" based on a single probe.** Symptoms to distinguish:

| Probe result | Likely cause | Action |
|---|---|---|
| `alert_value = N/A`, `severity = unknown` | Search ran, but no data row matched this KPI's entity (correct outcome on a service whose entities have no data) | Verify in O11y / source whether that entity actually emits the metric. If not, the KPI is correctly N/A — not a bug |
| `alert_value = <number>`, `severity = normal/info/...` | Search ran, data matched, KPI working ✓ | Done |
| `NO ROWS` in `itsi_summary` for the kpiid in last 10m, AND `_internal sourcetype=scheduler` shows the backing search succeeded recently | KPI's runtime registration didn't refresh. Re-PUT the service to force re-registration; wait another cycle | If still nothing after re-PUT + 2 cycles, dig into Step 4 stale fields |
| `NO ROWS` AND scheduler log shows recent `status=skipped` for the backing search | Search head is overloaded — your KPI may be fine; the search just didn't run | Wait. Check the UI in Service Analyzer (which uses different query paths) before concluding the KPI is broken |

**Lesson from a 2026-06 project**: my REST probe declared 16 of 20 KPIs broken; the user opened the UI and confirmed all the AppA Oracle KPIs were actually showing data. The search head was working through its backlog and my probe windows were too short. **Always cross-check the UI before iterating fixes**, especially on a degraded search head — the UI's Service Analyzer queries different summary windows and is more forgiving of recent gaps.

#### 6. Disable the predecessor base searches (don't delete)

The kpi_base_search KV-store object itself has no `disabled` flag. To stop the scheduler load, disable the **backing saved search** that ITSI generates for it. The naming convention is `Indicator - Shared - <kpi_base_search _key> - ITSI Search`, and these saved searches live in the `itsi` app namespace (NOT `SA-ITOA`).

```bash
# For each kpi_base_search to disable:
KEY=6a22c6dc0b6701132d00fae3
SS_NAME="Indicator - Shared - $KEY - ITSI Search"
SS_ENC=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$SS_NAME")
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/itsi/saved/searches/$SS_ENC/disable"
```

Verify by re-fetching the saved search and checking `disabled=True, is_scheduled=True` — note `is_scheduled` STAYS true (it's a property of the schedule definition, not the runtime state); `disabled` is what gates execution. After disable, no further `scheduler` log entries for that saved search.

**Why disable, not DELETE the `kpi_base_search`?**
- Disable is reversible — toggle `disabled=False` on the saved search to bring it back instantly
- Disable preserves the `kpi_base_search` KV definition, so if you ever need to re-attach a KPI to it, the definition is there
- `DELETE` on `kpi_base_search` works but is destructive — you'd recreate from scratch on rollback
- Splunk Cloud doesn't allow modifying / deleting saved searches shipped by signed apps, but DOES allow `disable` POST — so disable works on Cloud where delete may fail

#### 7. ITSI's auto-cleanup of orphaned backing saved searches

A pleasant surprise: when you repoint ALL the KPIs away from a `kpi_base_search` (leaving zero consumers), ITSI sometimes **auto-removes the backing saved search** in the next refresh cycle. The `kpi_base_search` KV definition stays, but the scheduled search disappears. This means one of your six predecessor disables may return 404 — that's not an error, the search is already gone.

Don't rely on this for cleanup planning (it doesn't always trigger), but don't be alarmed when it does happen.

### The tablespace exception — when full consolidation isn't possible

In the reference Oracle case, six of the seven SIM Oracle base searches consolidated cleanly into one. The seventh — `SIM Oracle DB Tablespace (Fixed)` — could NOT join the consolidated base search because it needs to break down by `tablespace_name`, which is an extra dimension beyond `(host, instance)`. Adding `tablespace_name` to the `by` clause of the consolidated SPL would multiply every other column's row count by the tablespace count, blowing up cardinality and breaking the existing per-host aggregations.

**Pattern**: if a metric family inherently needs a finer-grained `by` than the rest of your consolidated set, that's a hard signal to keep it on its own base search. Examples that typically can't consolidate:
- Tablespace usage (per-tablespace dim)
- Per-database queue depth (per-database dim)
- Per-NIC network counters (per-interface dim, when the base set is per-host)
- Per-partition disk usage (per-mount dim)

For those, leave the original base search running, document it as deliberate ("kept separate due to cardinality"), and the 2-3 KPIs that depend on it continue to use it. The consolidation win is still valuable on the other 80% of KPIs.

### Net result on a real cleanup (2026-06)

- **6 of 7** redundant Oracle base searches disabled (5 explicitly + 1 auto-cleaned by ITSI)
- **1 of 7** kept deliberately (the tablespace one)
- Each disabled search ran every 15 min → **~24 fewer scheduled search runs per hour** reclaimed for the search head
- The consolidated base search already existed (running every 5 min, 12/hour) → no net new load added
- All Fulfilment Oracle KPIs continued to function (verified in UI; REST probes lagged due to search head catch-up)
- Total session time: ~90 min (50 min of which was diagnosing the four hidden-state fields the first time)

The hidden-state lessons from this session are why this skill exists in its current form. The lessons table above lets the next session do this work in 20-30 min instead of 90.

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Building components via REST but forgetting to set `sec_grp: "default_itsi_security_group"` (Global) | Wizard packages the objects but on install, other teams can't see them (filtered by their security group) | Always set `sec_grp` to Global on CP-shipped objects |
| Selecting the SIM CP parent service (e.g. APM) in the wizard | Wizard pulls the entire SIM tree into your CP; export is huge; install conflicts with the SIM CP on the target | Select only YOUR leaves at the bottom of the tree |
| Forgetting `is_partial_data=1` when patching the SIM parent service | POST replaces the entire SIM service object, wiping SIM CP children; SIM CP reinstall required | Always use `?is_partial_data=1` for any non-greenfield service edit |
| Skipping Phase 3 verification — going straight from REST to wizard | Wizard packages broken objects; install on target replicates the broken state; debug cycle starts over on a fresh env | Run all 4 Phase-3 checks, even when in a hurry |
| Setting `is_metric: true` on a consolidated base search | Base search silently rejected; KPIs gray; no error logged anywhere | Default to `is_metric: false`; see `splunk-itsi-kpi-creation-via-api` |
| Using lowercase `entity_type: "os hosts"` because that's what SIM ships | Service binds zero entities; KPIs silent | Use verbatim case (`"OS Hosts"`); query the entity store first |
| Bumping the CP version on install but reusing the same `_key`s | Target env shows duplicate-key errors on KV store import | Always generate fresh UUIDs per object when building in a fresh env (don't reuse keys from another env) |
| Leaving `source_itsi_da` populated to the SIM app name on objects you authored | Objects appear locked/uneditable in the ITSI UI on the target env | Set `source_itsi_da: ""` on all custom objects before packaging |
| Authoring KPIs against a base search whose `_key` you didn't pin | Wizard pulls in the base search but its `_key` regenerates on install, breaking the KPI's `base_search_id` reference | Verify the wizard's exported `itsi_kpi_template.conf` references the base search by stanza name (it should); never hand-edit the `_key` |
| Disabling predecessor base searches BEFORE installing the CP | Brief outage between disable and install; SIM CP dashboards show no data | Install the CP first, verify KPIs colored, THEN disable predecessors |
| Including customer-specific values (CMDB lookups, perimeter values) in the CP | CP is no longer reusable across customers | Keep CMDB lookups in a separate per-customer app; ship only the platform-generic objects in the CP |
| **(Phase 5b)** Repointing a KPI's `base_search_id` and assuming the other fields auto-reconcile | `PUT` returns 200; KPI silently emits zero events because `entity_alias_filtering_fields` is `null` or `target_field` still points at the old column | After repoint, always cleanup the four hidden-state fields per the Phase 5b Step 4 table |
| **(Phase 5b)** Concluding a KPI is broken because `itsi_summary` probe returns no rows | The scheduler is just backed up (the very perf issue you're fixing); KPI is actually fine in the UI | Cross-check Service Analyzer UI before iterating fixes; check `_internal sourcetype=scheduler status=skipped` for the backing search |
| **(Phase 5b)** Trying to `DELETE` a `kpi_base_search` to stop its load | Splunk Cloud rejects destructive ops on signed-app savedsearches; or you lose the definition and can't roll back | Disable the **backing saved search** at `/servicesNS/nobody/itsi/saved/searches/Indicator - Shared - <key> - ITSI Search/disable` |
| **(Phase 5b)** Targeting `/servicesNS/nobody/SA-ITOA/...` for the saved-search disable | 404 — the backing saved search lives in the `itsi` app namespace, not `SA-ITOA` | Use `/servicesNS/nobody/itsi/saved/searches/...` |
| **(Phase 5b)** Trying to consolidate a tablespace / per-NIC / per-partition base search into the main one | Cardinality explosion: every other column's row count is multiplied by the new dimension | Recognize the cardinality blocker, keep the high-dim base search separate, document as deliberate |
| **(Phase 5b)** Verifying the extended consolidated SPL by prefixing `search ` to a `| mstats ...` string | Splunk error: "This command must be the first command of a search" — `mstats` is a generating command, not a streaming one | Run the SPL as-is; do not prefix `search ` when the first token is already a `|` generating command |

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Writing the CP's `.conf` files by hand instead of using the wizard | Brittle; easy to miss required fields; doesn't validate against ITSI's KV-store schema; no way to test before export | Always build live in ITSI, run the wizard. The wizard handles the conf serialization correctly |
| One giant CP bundling everything custom for a customer | Hard to install selectively; updates ship as all-or-nothing; long install reviews | Smaller, focused CPs per logical domain |
| Versioning by date (`2026-06-10`) instead of semver | Can't tell what changed between versions; hard to communicate breakage | Use semver (`1.0.0`, `1.1.0`, `2.0.0`); track changes in CHANGELOG.md |
| Skipping the README and BUG_FIXES files | Future consultants don't know what the CP does, what versions it was tested against, or what's broken | Always document. 30 minutes upfront saves hours of forensics later |
| Treating Phase 5 cleanup as optional | The CP's value to the customer is partly the search-head load reduction from disabling predecessor objects; without cleanup, you've added objects without removing the redundant ones | Always disable predecessors as part of the install playbook |
| Modifying the shipped SIM content pack instead of forking via overlay CP | Next Splunk Cloud admin-portal upgrade silently reverts your changes | Ship a separate overlay CP (`DA-ITSI-CP-sim-os-hosts-fixed`, your DB monitoring CP, etc.) — never edit shipped content |
| Selecting "all services" in the wizard "to be safe" | Pulls in other consultants' content; export is huge; install fails on the target env due to objects already present | Select only the services that are YOURS to ship |

## Related skills

- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities (prereq)
- `splunk-itsi-service-tree-design` — perimeter/rollup/leaf design + leaves-first ordering + `is_partial_data=1` (used in Phase 2)
- `splunk-itsi-kpi-creation-via-api` — KPI + kpi_base_search authoring including the `is_metric` trap (Killer 2)
- `splunk-itsi-entity-binding-architecture` — why entity-rule case sensitivity (Killer 1) matters at the architecture level
- `splunk-itsi-entity-cmdb-lookup` — the upstream CMDB lookup that drives `service` info-field values used in entity rules
- `otel-vs-splunk-ingestion` — context for what data sources the CP's base searches will run against
