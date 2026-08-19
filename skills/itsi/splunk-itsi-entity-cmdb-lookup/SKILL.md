---
name: splunk-itsi-entity-cmdb-lookup
category: itsi
description: Build and maintain a small CSV-based mini-CMDB lookup in Splunk ITSI to enrich entities with business context (perimeter, application, service, ownership) that machine data alone cannot provide. Drives dynamic entity filtering for infrastructure KPIs across multiple perimeters, identifies unmapped/unknown hosts via a scheduled mismatch-audit saved search, and stays editable by a human via the Lookup Editor add-on. Covers the Splunk-Cloud-safe creation pattern (`outputlookup createinapp=true` from a search instead of REST file upload), the multi-row-per-host pattern for hosts that belong to multiple services (e.g. one TIBCO box hosting both BW and EMS), the requirement to expose an alias-type identifier (e.g. ITSIUniqueId) on each entity to make service entity filtering work, the entity-type-name matching gotcha (must equal ITSI's stored entity types verbatim — typically `OS Hosts` or `Azure VM`), the case-insensitive matching gotcha, two consumption patterns (direct `lookup` in KPI search vs ITSI Entity Import for service entity rules), and the host-join-key pitfalls (FQDN drift, hash-suffixed entity titles, case mismatches, SignalFx-style dimensions vs `host`). Use when designing the "glue" between machine data and business perimeters in ITSI, when the user mentions entity tagging / perimeter filtering / entity rules / dynamic KPI scope / mini-CMDB / lookup-based enrichment / service column / multi-membership, when an entity import or info field approach is being considered, or when KPI searches need to be scoped to a subset of hosts that share a business attribute not present in the data stream.
disable-model-invocation: true
---

# ITSI Entity CMDB Lookup

How to build and maintain a small, human-editable CSV lookup that adds the business context (perimeter, application, ownership) that machine data doesn't carry — and that drives dynamic entity filtering in infrastructure KPIs.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use this skill

- A deployment spans multiple business perimeters but the data stream alone (CPU, memory, network) can't tell you which perimeter a host belongs to
- The user mentions "dynamic filtering of entities", "perimeter/application/owner tagging", "mini-CMDB", "lookup-based entity enrichment"
- KPI searches need to scope to a subset of hosts based on attributes not in the metrics
- New OTel/UF deployments are happening and you need a way to flag unknown hosts as they appear in ITSI
- An ITSI Entity Import is being considered to add info fields to entities

Prerequisite: REST access to the ITSI SH (see `splunk-itsi-api-access`).

## The shape of the solution

```
                                                            ┌─────────────────────────────┐
┌─────────────────────────────────┐                          │   ITSI                      │
│ entity_cmdb.csv (source of truth)│                          │                             │
│   host                          │  consumed two ways:      │  (a) KPI searches use       │
│   entity_type                   │  ────────────────────►   │      | lookup entity_cmdb   │
│   perimeter                     │                          │      host AS extracted_host │
│   application                   │                          │      OUTPUT perimeter ...   │
│   notes                         │                          │                             │
└─────────────────────────────────┘                          │  (b) Optional Entity Import │
       ▲                                                     │      pushes columns as      │
       │ edited via Lookup Editor add-on                     │      info_field_<x> on      │
       │ (Splunk-supported, runs in browser)                 │      entities for service   │
       │                                                     │      entity rules.          │
   Human owner                                               └─────────────────────────────┘
                                                                          │
                                                              ┌───────────┴────────────┐
                                                              ▼                        ▼
                                                       Scheduled Audit          KPI scoping
                                                       Search detects:          |where perimeter="TIBCO"
                                                       - ITSI_NOT_IN_CMDB
                                                       - CMDB_ORPHAN_NOT_IN_ITSI
                                                       - PERIMETER_UNKNOWN
```

## Keep the schema small

Resist the urge to over-engineer this on day 1. Six columns is the proven sweet spot — the v3 schema:

| Column | Required | Purpose |
|---|---|---|
| `host` | Yes | Join key against the data side. **Use the exact form ITSI sees** (see "join key pitfalls" below). |
| `entity_type` | Yes | **MUST match an ITSI entity type verbatim.** Sanity check with `\| inputlookup itsi_entities \| stats count by entity_type`. Typical Splunk-shipped values: `OS Hosts`, `Azure VM`, `Kubernetes Node`. Do NOT use free text like `Server` — ITSI rule-matching is **literal** on this field |
| `perimeter` | Yes | Drives KPI/service entity rules at the perimeter rollup level. Reserved values: `UNKNOWN` (yet-to-classify), `OUT_OF_SCOPE` (not in scope), `SHARED` (multi-perimeter). Otherwise: free text matching your service tree (e.g., `TIBCO`, `MES`, `I2P`, `SAP`) |
| `application` | Yes (recommended) | Refines beyond perimeter. A TIBCO host can be `BusinessWorks` or `EMS`; a SAP host can be `SAP App`, `SAP DB`, `SAP SCS`, etc. |
| `service` | Yes | **The exact title of the ITSI Platform leaf** the host should bind to (e.g., `TIBCO-BW - Platform`). Drives the Layer-2 entity rule directly. Multi-membership is achieved by adding multiple rows (see "co-located services" below) |
| `notes` | No | Free text for the human maintainer. Not consumed by SPL |

What to defer until you need it: `environment`, `owner`, `tier`, `site`, `region`. Add only when the first concrete query asks for them.

### Why a `service` column instead of inferring from perimeter+application

Because the inference logic gets non-trivial fast:
- One TIBCO host runs both BW and EMS engines (two rows, two services)
- "SAP DB" actually maps to multiple Platform leaves (one per SID)
- The relationship "perimeter + application → service" is many-to-many in real environments

A `service` column makes the mapping explicit, human-auditable, and trivially consumed by the Entity Import (no SPL gymnastics to compute the target service name).

### Co-located services (multi-membership)

When a single physical host belongs to multiple ITSI services, add multiple rows to the CMDB — one row per (host, service) tuple:

```csv
host,entity_type,perimeter,application,service,notes
tibhost01.example.com,OS Hosts,TIBCO,BusinessWorks,TIBCO-BW - Platform,
tibhost01.example.com,OS Hosts,TIBCO,EMS,TIBCO-EMS - Platform,Co-located on same VM
tibhost02.example.com,OS Hosts,TIBCO,BusinessWorks,TIBCO-BW - Platform,
tibhost02.example.com,OS Hosts,TIBCO,EMS,TIBCO-EMS - Platform,Co-located on same VM
```

The Entity Import step (Pattern B below) handles multi-row → multi-value info fields natively. ITSI stores `service` as a multi-valued info field. Rule matching on `info.service matches "tibco-bw - platform"` matches as long as ONE of the multi-values matches — so the host shows up under BOTH services. Same for `perimeter` and `application` if a host genuinely spans them.

Do NOT try to encode multi-membership with delimited strings (`service="TIBCO-BW - Platform|TIBCO-EMS - Platform"`). ITSI rule matching is per-value, not substring; the delimited form never matches.

## Step 1 — Seed the CMDB from ITSI itself

Don't start with an empty CSV. Pull the current entity inventory from ITSI's own `itsi_entities` KV-store-backed lookup, classify by hostname pattern, and you'll bootstrap to ~95% accuracy in minutes.

`itsi_entities` is the canonical ITSI entity store (app: `SA-ITOA`, type: `kvstore`, collection: `itsi_services`). The schema:

```python
import json, re
from collections import defaultdict

# After: curl ... /servicesNS/nobody/SA-ITOA/itoa_interface/entity?count=500 -> entities.json
items = json.load(open('entities.json'))
items = items if isinstance(items, list) else items.get('entry', [])

inv = defaultdict(lambda: {"types": set(), "n": 0})
for e in items:
    et    = e.get('entity_type', '')
    title = e.get('title', '')
    ident_vals = (e.get('identifier') or {}).get('values', [])
    if not ident_vals: continue
    raw = str(ident_vals[0])

    if et == 'OS Hosts':
        # Strip the _HJPjeYQCgAA-style hash suffix added by the SIM add-on
        host = re.sub(r'_[a-z0-9]{10,12}$', '', raw)
    elif et == 'Azure VM':
        # The Azure resource path; resource name is after /virtualmachines/
        m = re.search(r'/virtualmachines/([^:/]+)', raw)
        host = m.group(1) if m else raw.split('/')[-1].split(':')[0]
    else:
        host = raw
    host = host.lower()
    inv[host]['types'].add(et)
    inv[host]['n']  += 1

# Then classify by naming pattern -> perimeter, application
```

Two things this extraction handles that you'll otherwise miss:

1. **Hash suffix on ITSI entity titles.** SIM appends `_HJPjeYQCgAA`-style 11-char base62 hashes for deduplication. The clean hostname is in `identifier.values` after stripping the suffix.
2. **Azure VM titles are bare UUIDs/resource paths.** The real name is the segment after `/virtualmachines/`. The same physical host shows up as BOTH an `Azure VM` and an `OS Hosts` entity — deduplicate to one row keyed on `host`.

Classification by naming pattern is a one-time heuristic. For Acme-shaped environments:

| Pattern | Likely perimeter | Likely application |
|---|---|---|
| `azsap*`, `desap*`, `azeunodfesap*` | SAP | `SAP App` / `SAP DB` / `SAP SCS` / `SAP Backup` (substring match) |
| `iltib*` (with `glb`) | TIBCO | `BusinessWorks` / `EMS` (refine manually) |
| `ilmesdev*` | MES | `MES App` / `MES Background` / `Citrix` (substring match) |
| `ilinvoice*` | I2P | `I2P App` |
| `ilredpd*` | I2P | `ReadSoft` |
| `ilsqlcons*`, `ilconsdb*` | SHARED | `SQL Server` |
| `desktop-*` | OUT_OF_SCOPE | — |
| Short IDs (≤4 chars: `ed3`, `ld1`) | SAP | SAP System ID (PowerConnect logical entities) |
| Everything else | UNKNOWN | UNKNOWN |

## Step 2 — Create the CSV file (Splunk Cloud safe)

Direct CSV upload via `POST /data/lookup-table-files` requires the file to live in the staging area `/opt/splunk/var/run/splunk/lookup_tmp/` first — which you can't reach in Splunk Cloud. The Cloud-safe pattern is to use a search that runs `| outputlookup` server-side.

Encode the CSV rows into a single string (use `|` as row separator since values don't contain `|`, and `,` as field separator), then:

```spl
| makeresults
| fields - _time
| eval rows=split("host,entity_type,perimeter,application,notes|azsapapp01ad3,Azure VM,SAP,SAP App,...|...", "|")
| mvexpand rows
| rex field=rows "(?<host>[^,]*),(?<entity_type>[^,]*),(?<perimeter>[^,]*),(?<application>[^,]*),(?<notes>.*)"
| fields host, entity_type, perimeter, application, notes
| outputlookup createinapp=true entity_cmdb.csv
```

POST that as a search to `/servicesNS/nobody/SA-ITOA/search/jobs` with `exec_mode=blocking`. The `createinapp=true` flag writes the file into the search context's app — so the namespace `nobody/SA-ITOA` lands it in `$SPLUNK_HOME/etc/apps/SA-ITOA/lookups/entity_cmdb.csv`.

For a one-off seed of ~50-200 hosts the inline-eval approach is the simplest. For larger seeds, write the CSV to a temp file first, then use `| inputcsv` in a one-shot dispatch search.

## Step 3 — Create the lookup definition

The CSV file alone is enough for `| inputlookup entity_cmdb.csv` to work, but you need a named lookup definition for the `| lookup <name> ...` syntax used in KPI searches:

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/data/transforms/lookups" \
  --data-urlencode "name=entity_cmdb" \
  --data-urlencode "filename=entity_cmdb.csv" \
  --data-urlencode "case_sensitive_match=false"
```

**Critical**: set `case_sensitive_match=false` at create time. Hostname casing drifts wildly between data sources (`SAPHOST01.Example.Com` from one collector, `saphost01.example.com` from another). Without case-insensitive matching, half your joins will silently fail.

**Don't omit the `type` argument.** Some Splunk docs show `type=file_based` — that argument isn't supported by this endpoint and the create will 400.

## Step 4 — Verify before you build dependent things

Three quick checks:

```bash
# A. The lookup definition is visible
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/services/data/transforms/lookups?search=name=entity_cmdb&output_mode=json" \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('entry',[])), 'definitions found')"

# B. The lookup file is queryable
SID=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/search/jobs" \
  -d "search=| inputlookup entity_cmdb | stats count by perimeter" \
  -d "exec_mode=blocking" -d "output_mode=json" | python3 -c "import sys,json;print(json.load(sys.stdin)['sid'])")
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/services/search/jobs/$SID/results?output_mode=json"

# C. The KPI-search-style join actually resolves hosts (use a metric you KNOW exists)
| mstats count WHERE index=sim_metrics AND metric_name=memory.free earliest=-30m BY extracted_host
| lookup entity_cmdb host AS extracted_host OUTPUT perimeter
| eval perimeter=coalesce(perimeter,"UNMAPPED")
| stats dc(extracted_host) as n_hosts by perimeter
```

If `UNMAPPED` is non-zero, you have hosts in the data that aren't in the CMDB — that's the audit feeding source.

## Step 5 — Create the scheduled mismatch audit

This is the "flag unknowns" piece. A daily saved search that surfaces three kinds of drift:

```spl
| inputlookup itsi_entities
| eval inf_string=mvjoin(_itsi_informational_lookups, "###")
| rex field=inf_string "extracted_host=(?<host_os>[^#]+)"
| rex field=inf_string "resourcename=(?<host_az>[^#]+)"
| eval host=coalesce(host_os, host_az, lower(title))
| eval host=lower(host)
| fields host, entity_type, title | dedup host
| eval in_itsi="yes"
| append [
    | inputlookup entity_cmdb.csv 
    | eval host=lower(host), in_cmdb="yes" 
    | fields host, in_cmdb, perimeter, application
  ]
| stats values(entity_type) as entity_type, values(title) as itsi_title,
        values(in_itsi) as in_itsi, values(in_cmdb) as in_cmdb,
        values(perimeter) as perimeter, values(application) as application
        by host
| eval flag=case(
    in_itsi="yes" AND isnull(in_cmdb),    "ITSI_NOT_IN_CMDB",
    isnull(in_itsi) AND in_cmdb="yes",    "CMDB_ORPHAN_NOT_IN_ITSI",
    perimeter="UNKNOWN",                   "PERIMETER_UNKNOWN",
    perimeter="OUT_OF_SCOPE",              "INFO_out_of_scope",
    1=1,                                   "OK")
| where flag!="OK" AND flag!="INFO_out_of_scope"
| table flag, host, perimeter, application, entity_type, itsi_title
| sort flag, host
```

Save it as `CMDB - Entity Mismatch Audit` with `cron_schedule = 0 6 * * *` (daily at 06:00 UTC), `is_scheduled=1`. Don't attach an alert action initially — the SE / consultant reviews results on demand. Add a Slack/email alert later if drift becomes routine.

The three flags:

| Flag | Meaning | Action |
|---|---|---|
| `ITSI_NOT_IN_CMDB` | New entity in ITSI without a CMDB row | Add a row (or accept as OUT_OF_SCOPE) |
| `CMDB_ORPHAN_NOT_IN_ITSI` | CMDB row whose host doesn't exist in ITSI anymore | Host decommissioned? typo in CMDB? FQDN/short drift? |
| `PERIMETER_UNKNOWN` | CMDB row present but not yet classified | Lookup Editor → set perimeter |

## Step 6 — Consume in KPI searches

Two consumption patterns. Pick based on whether you want the enrichment in the KPI search or in the entity store.

### Pattern A — Direct lookup in KPI search (simple, immediate)

```spl
| mstats avg(memory.utilization) as mem_pct
    WHERE index=sim_metrics AND metric_name=memory.utilization earliest=-15m
    BY extracted_host
| lookup entity_cmdb host AS extracted_host OUTPUT perimeter, application
| where perimeter="TIBCO" AND application="BusinessWorks"
| timechart avg(mem_pct) BY extracted_host
```

**Pros**: zero ITSI configuration, immediate effect of CSV edits.  
**Cons**: every KPI search carries the `lookup + where` boilerplate, the entity rule UI doesn't see the perimeter.

### Pattern B — ITSI Entity Import (cleaner UX in service rules)

Configure an ITSI Entity Import (Settings → Configure Entities → Import via Search) that runs this saved search and maps the columns:

```spl
| inputlookup entity_cmdb.csv
| eval entity_title=host
| eval identifier_field_ITSIUniqueId=host
| eval identifier_field_extracted_host=host
| eval informational_field_perimeter=perimeter
| eval informational_field_application=application
| eval informational_field_service=service
| stats values(*) as * by entity_title, entity_type
| table entity_title, entity_type, 
        identifier_field_ITSIUniqueId, identifier_field_extracted_host,
        informational_field_perimeter, informational_field_application, informational_field_service
```

Then in the ITSI Entity Import UI, map:
- `entity_title` → Title field
- `entity_type` → Entity Type field (must match values in ITSI's entity_type definitions)
- `identifier_field_ITSIUniqueId` → Identifier field (alias) — **CRITICAL for Layer 2 entity rule matching, see `splunk-itsi-entity-binding-architecture`**
- `identifier_field_extracted_host` → Identifier field (alias, optional secondary)
- `informational_field_perimeter` → Informational field `perimeter`
- `informational_field_application` → Informational field `application`
- `informational_field_service` → Informational field `service` (drives the entity rule on each Platform leaf)

Set the import to **Append/Merge** (not Replace) so the SIM-created entities keep their existing identifiers and gain the new info fields. Schedule for hourly.

The `stats values(*) as * by entity_title, entity_type` pre-aggregation step is what handles the multi-row co-location pattern: if a host has 2 CMDB rows (BW and EMS), the resulting entity has multi-valued `service` info field with both leaf names. ITSI rule matching on either leaf's rule will match this entity.

After the first run, your KPI entity rules in the service tree can match on `info.service == "tibco-bw - platform"` natively (note: ITSI lowercases info values on import — match on lowercase).

**Pros**: clean UX in service rules, info fields visible in entity detail page, multi-membership works natively.  
**Cons**: requires UI configuration, hourly lag from CSV edit to entity update.

### Why `identifier_field_ITSIUniqueId` is required (not optional)

ITSI's "service entity filter" mechanism (Layer 4 in `splunk-itsi-entity-binding-architecture`) injects a WHERE clause into the base search at runtime, of the form:

```spl
... AND ITSIUniqueId IN (val1, val2, ...)
```

It picks the alias field named in the entity rule's `field_type=alias` clause. If your entities don't have that alias populated, the WHERE clause has no values to inject, the filter silently degrades to "no filter", and the KPI shows ALL hosts in the data — not just the bound ones.

So the import MUST populate the `ITSIUniqueId` alias on every entity, even if the value is the same as the entity title. It's the join key for Layer 2 → Layer 4.

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Using `host` dimension in `mstats` instead of `extracted_host` | All metrics roll up to `http-inputs-<stack>.splunkcloud.com` | Use `extracted_host` (data-center hosts) or `azure_computer_name` (Azure) — `host` in SIM data is the HEC endpoint, not the source host |
| Case-sensitive lookup matching | Half the hosts resolve as `UNMAPPED` | `case_sensitive_match=false` on the lookup definition |
| FQDN vs short hostname drift | Some entries map, others don't | Either normalize at the lookup edge (add `| eval host=lower(host) \| eval host=replace(host, "\\..*$", "")` before the join, dropping the FQDN part) or maintain BOTH forms as separate rows in the CSV. Document the choice prominently |
| Hash-suffixed entity titles in ITSI | Discovery script can't match anything | Strip the `_[a-z0-9]{10,12}$` suffix when reading from `identifier.values` |
| Azure VM titles are full resource paths | Title-based join fails | Use `ResourceName` info field, or extract from the path with `rex "/virtualmachines/(?<host>[^:/]+)"` |
| Direct CSV upload via REST returns "Source file is outside of staging area" | Splunk Cloud blocks direct file uploads to the lookup-table-files endpoint | Use `| outputlookup createinapp=true` from a search instead |
| Lookup definition creation succeeds but later updates 404 ("Could not find object") with creates 400 ("already exists") | Splunk Cloud KV/transforms cache is in a stuck state | Create under a different name with a version suffix (`entity_cmdb_v1`), set ACL `sharing=app owner=nobody` immediately. The ghost is harmless and clears itself eventually |
| ITSI Entity Import overwrites the SIM identifier fields | Existing SIM entities lose their alias to the data | Set the import to **Merge / Append** mode, not Replace. Map only NEW info fields, not identifiers |
| Multi-perimeter hosts (e.g., shared DB) | One row in CMDB, but the host is monitored under two services | Use the multi-row pattern: one row per (host, service) tuple. The entity import's `stats values(*) as * by entity_title` aggregates them into a single entity with multi-valued info fields. ITSI rule matching honors per-value membership |
| `entity_type` value doesn't match an ITSI entity type | Entity Import creates entities but they never get bound to any service (rule type-check fails) | Verify with `\| inputlookup itsi_entities \| stats count by entity_type` — typical values are `OS Hosts`, `Azure VM`. Use EXACTLY that spelling in your CMDB. Free text like `Server` won't match |
| Missing the `ITSIUniqueId` identifier in the Entity Import mapping | Entities created/updated but service-level KPI filtering doesn't work; KPI shows all hosts in data | Always map an `identifier_field_ITSIUniqueId` column. The alias is required for Layer 2/4 binding (see `splunk-itsi-entity-binding-architecture`) |

## Editing via Lookup Editor

Install [Lookup Editor (Splunkbase)](https://splunkbase.splunk.com/app/1724) in the SH. After install:

- Settings → Lookup Editor → pick `entity_cmdb.csv` (filter by app: `SA-ITOA`)
- Edit cells inline, save with one click
- Save creates a new version in `.csv` (history kept per-edit, viewable via the History tab)

For multi-user environments, set the lookup permissions to `read=*, write=admin` (or a specific role) to avoid accidental edits.

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Editing `itsi_entities` directly via Lookup Editor | It's a KV-store-backed lookup auto-managed by ITSI imports. Manual rows can be overwritten on the next sync; schema isn't yours to extend | Keep `itsi_entities` as ITSI's, create a separate CMDB CSV that you own |
| Adding 10+ columns "for future use" | CMDB becomes hard to maintain, encourages stale data, slow to load | 5 columns. Add the 6th only when a concrete query needs it |
| Putting the CMDB in a brand new app instead of `SA-ITOA` | Adds an app to maintain, ACL gymnastics across apps, lookup name visibility issues | On a dev instance, put it in `SA-ITOA`. Migrate later if/when productionized |
| Skipping the seed step and starting from an empty CSV | Adoption never happens — humans don't want to type 50+ rows from scratch | Always seed from `itsi_entities` first, then let humans REVIEW + EDIT, not CREATE |
| Hardcoding hostnames in KPI searches "just for now" | You'll forget; new hosts won't be picked up; "just for now" becomes permanent | Even with 3 hosts, route through the CMDB. The pattern is cheap and growth-proof |
| Storing the CMDB in the metric data via OTel processor attributes | Distributed maintenance across N collectors, no central edit, no audit | Central CSV. The collectors stay generic |
| Setting up the Entity Import before the basic lookup-in-KPI pattern is proven | Two moving parts at once → twice the debug surface | Pattern A first (lookup in KPI search), prove the join works, THEN add Pattern B if needed |

## Related skills

- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities (prereq)
- `splunk-itsi-entity-binding-architecture` — why the `service` column + `ITSIUniqueId` alias must be wired correctly for KPI scoping to work
- `splunk-itsi-service-tree-design` — the Platform leaves that the `service` column points at
- `splunk-itsi-kpi-creation-via-api` — how KPIs on those Platform leaves consume the info fields
- `otel-vs-splunk-ingestion` — what's producing the data the CMDB is enriching
