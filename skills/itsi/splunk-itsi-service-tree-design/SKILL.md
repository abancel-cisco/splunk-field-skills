---
name: splunk-itsi-service-tree-design
category: itsi
description: Design and safely build a Splunk ITSI service tree via the REST API without disturbing existing customer or co-worker content. Covers the perimeter-rollup-leaf design pattern for multi-system projects, the Platform + Functional + End-to-End pillar pattern under each perimeter (Platform = infra metrics from OS/cloud-VM data; Functional = app-specific KPIs from app logs/traces; E2E = cross-perimeter business transactions), the 3-phase safe-build flow (sandbox prefix -> human review in Service Topology -> in-place cutover by rename), leaves-first ordering for single-pass dependency wiring, the SHKPI-<key> service-health-KPI naming convention that all dependency payloads rely on, partial-update via `?is_partial_data=1` for non-destructive edits, the cross-team integration pattern (read-only refs to another owner's services without polluting their tree with sandbox names), bidirectional dependency verification, and stray cleanup. Use when building an ITSI service tree from scratch, integrating with an existing partial tree owned by another consultant/team, designing the parent service for a multi-perimeter solution, structuring sub-services under a perimeter (Platform vs Functional vs E2E), when the user mentions ITSI service topology / service tree / kpis_depending_on / SHKPI / sec_grp / service templates / Platform pillar / Functional pillar / End-to-End business transactions, or when working on the "glue" between heterogeneous data sources in ITSI.
disable-model-invocation: true
---

# Splunk ITSI Service Tree Design

How to design a service tree for a multi-perimeter solution and build it safely against a live ITSI instance — especially when other consultants already have content in there.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use this skill

- Designing the "service glue" for a solution that spans multiple systems (Buttercup-Middleware, Buttercup-ERP, Buttercup-Fulfilment, etc.)
- Joining an ITSI environment where another owner already has services and you must not touch theirs
- Bootstrapping a tree from REST API rather than the UI (faster, repeatable, version-controllable)
- Recovering from a half-built tree (orphan services, broken deps, prefix sprawl)
- The user mentions ITSI service topology, service tree, KPI dependencies, SHKPI, sec_grp, service templates

Prerequisite: REST access already working — see `splunk-itsi-api-access`. This skill assumes you can already POST to `/servicesNS/nobody/SA-ITOA/itoa_interface/service` and get a 200.

## Design principles

### 1. Three layers, no more on day 1 — but THREE PILLARS under each perimeter

The layer count stays at three (parent → perimeter → leaf). Inside each perimeter, organize the leaves into three pillars so the topology view is readable and KPI ownership is clear:

| Layer | Purpose | Examples | Has KPIs? |
|---|---|---|---|
| **Top parent** (1) | The programme | `Acme Observability` | No (rollup only) |
| **Perimeter rollups** (4-6) | One per business/system perimeter | `Buttercup-Middleware`, `Buttercup-Fulfilment`, `Buttercup-Invoicing`, `Buttercup-ERP`, `End-to-End Business Transactions` | Rollup only (no direct KPIs) |
| **Leaf services** (organized in 3 pillars per perimeter) | See pillar pattern below | YES — actual KPIs land here |

#### The three-pillar pattern (per perimeter)

```
Buttercup-Middleware  (perimeter rollup)
 ├── Platform                                        (infra metrics from OS/VM data)
 │    ├── Buttercup-Bus   - Platform                 ← 6 OS KPIs (CPU, Mem, Disk R/W, Net R/T)
 │    └── Buttercup-Queue - Platform                 ← 6 OS KPIs
 ├── Functional                                      (app-specific KPIs from app logs/traces)
 │    ├── Buttercup-Bus   - Integration Engines      ← e.g., process count, queue depth, errors/s
 │    └── Buttercup-Queue - JMS Queues               ← e.g., pending message count, throughput
 └── App Health      (optional)                      (combined health view, or alerting wrapper)
      └── Buttercup-Middleware - Overall App Health  ← rolls up Platform + Functional severities
```

Why three pillars (Platform / Functional / App Health):

| Pillar | Driven by | Owned by | Purpose |
|---|---|---|---|
| **Platform** | OS/cloud-VM data (CPU, memory, disk, network — usually SIM-fed) | Infra/Ops team | "Is the underlying host healthy?" Generic across applications |
| **Functional** | App-specific data (logs, traces, custom metrics) | App owner | "Is the application doing its job?" Specific to each application |
| **App Health** | Rollup of Platform + Functional via `services_depends_on` | App owner | Single severity for executive view, alerting, ITSI Glass Tables |

This separation is what lets you say "the Platform is fine but the Functional has alarms" — a sentence operations teams actually need to say.

Resist the temptation to go 4 levels deep on day 1 (e.g., adding a "Buttercup-Fulfilment → Buttercup-Orders → Buttercup-Orders - Platform → Buttercup-Orders - Platform - Linux Hosts"). You can always insert intermediate layers later; you cannot easily collapse them. The Service Topology view also gets unreadable past 3 layers wide for a single perimeter.

### 1b. The "End-to-End Business Transactions" perimeter

A 5th-or-6th sibling perimeter (peer of Buttercup-Middleware/Buttercup-Fulfilment/Buttercup-ERP/etc.) dedicated to cross-perimeter user journeys:

```
End-to-End Business Transactions  (perimeter rollup)
 ├── Order-to-Cash                  ← spans Buttercup-ERP → Buttercup-Middleware → Buttercup-Fulfilment → Buttercup-Invoicing
 ├── Procure-to-Pay                 ← spans Buttercup-Invoicing → Buttercup-ERP → Buttercup-Fulfilment
 ├── Invoice Processing             ← spans Buttercup-DocCapture → Buttercup-ERP-App → Buttercup-ERP-DB
 └── ...
```

Each E2E leaf has KPIs measuring user-perceived metrics (transaction latency, error rate, completion %) plus `services_depends_on` references to the underlying perimeter leaves whose health affects the journey. This makes "executive view" a one-glance answer.

KPI sources for E2E:
- Trace data from OTel collectors instrumenting the user-facing edge
- Synthetic transaction probes (k6, Locust)
- Application logs with business-transaction IDs
- BAM-style derivation from message queues or DB tables

### 2. Naming convention is your contract

Pick a convention before you create anything and stick to it. The one we settled on for Acme (and recommend for similar deployments):

```
<PERIMETER>[-<SUBSYSTEM>] - <PILLAR>
  Buttercup-Middleware                     ← perimeter rollup, no pillar suffix
  Buttercup-Bus - Platform                 ← leaf, "Platform" pillar
  Buttercup-Bus - Integration Engines      ← leaf, "Functional" pillar (no suffix, but a descriptive title)
  Buttercup-Queue - Platform
  Buttercup-Queue - JMS Queues             ← Functional leaf
  Buttercup-Orders - Platform
  Buttercup-Batch - Platform
  Buttercup-Desktop - Platform
  Buttercup-Invoices - Platform
  Buttercup-DocCapture - Platform
  Buttercup-ERP-App - Platform             ← (owned by another consultant in the example)
  End-to-End Business Transactions         ← top-level perimeter for E2E
  Order-to-Cash                            ← E2E leaf
```

Why this works:
- Alphabetical sort groups perimeter+subsystem together in the picker
- The `- Platform` suffix is grep-able for bulk operations (`filter by title regex "- Platform$"`)
- The rollup is always shorter than its leaves (visual scanning)
- The program-level parent (`Acme - ...`) sorts above everything

What to avoid: `ITSI-`, `SVC-`, `Acme-` prefixes — they add no information and waste 5 chars on every screen.

### 2b. Standard suffixes by pillar

| Pillar | Suffix convention | Example |
|---|---|---|
| Platform | `- Platform` (always exactly this) | `Buttercup-Orders - Platform` |
| Functional | descriptive title, no canonical suffix | `Buttercup-Orders - JBoss Processes`, `Buttercup-Orders - JVM Metrics` |
| App Health (optional rollup) | `- App Health` | `Buttercup-Fulfilment - App Health` |
| E2E | descriptive business-transaction name | `Order-to-Cash`, `Invoice Processing` |

The Platform suffix is rigid because it drives the bulk Layer-2 entity rule (`info.service matches "<lowercased title>"`) and the bulk replication script in `splunk-itsi-kpi-creation-via-api`. Inconsistent suffixes break the automation.

### 3. Cross-team integration: read-only refs, never overwrite

The single most important rule when joining an environment that already has services from another owner (e.g., another consultant's ERP services):

> **Your tree depends on their services. Their tree never depends on yours.**

In ITSI REST terms: your service's `services_depends_on` array includes their `_key`. Their service's `services_depending_on_me` will be updated automatically by ITSI's KV store consistency — you don't post to their objects, ever.

This pattern survives them refactoring their tree, lets them delete sandbox content you created without breaking their work, and is the only ethically acceptable thing to do without their explicit sign-off.

## The 3-phase safe-build flow

This is the flow we executed for Acme and the one I'd repeat every time. It's slower than "just create the tree" by maybe 30 minutes, and saves you from a 4-hour cleanup if something is off.

```
┌──────────────────────────┐
│  Phase 1: Sandbox build  │  Create everything with SANDBOX-CURSOR- prefix.
│                          │  Within-sandbox deps only (no cross-team yet).
│                          │  Leaves-first ordering.
└────────────┬─────────────┘
             │
             ▼  (user opens Service Topology in UI)
┌──────────────────────────┐
│  Phase 2: Human review   │  User visually inspects the tree.
│                          │  Adjusts naming, structure, dep direction.
│                          │  Pattern is non-destructive — anything wrong
│                          │  can be deleted with one sweep on the prefix.
└────────────┬─────────────┘
             │
             ▼  (user explicitly approves)
┌──────────────────────────┐
│  Phase 3: Cutover        │  Strip prefix in-place (partial update).
│                          │  Wire cross-team deps.
│                          │  Delete drafts/old test services.
│                          │  Verify dep counts bidirectionally.
└──────────────────────────┘
```

### Phase 1: Sandbox prefix discipline

Every service created in phase 1 gets a clear prefix. We used `SANDBOX-CURSOR-`. The point is:
- Easy to grep for and bulk-delete if the design is rejected
- Visually obvious in the UI that these are not production
- Unique enough that the prefix won't collide with anything customer-created

> **Warning — this is a *naming* convention, not environment isolation.** Sandbox-prefixed services exist in the same KV store, same `sec_grp`, same backups as production. If you create a sandbox KPI that does a `count(*)` on `index=*`, it costs the same SVCs as a production one. Sandbox = labeled, not safer.

### Phase 1: Leaves-first ordering

ITSI dependencies are unidirectional, set at create time via `services_depends_on`. If A depends on B, you must create B first, capture its `_key`, then create A with that key in the deps array.

For a tree like:

```
Acme (top parent)
 ├── Buttercup-Middleware
 │    ├── Buttercup-Middleware - Integration Bus
 │    └── Buttercup-Middleware - Message Queue
 ├── Buttercup-Fulfilment
 │    └── Buttercup-Fulfilment - JBoss
 └── ...
```

Create order is leaves → rollups → parent:

```
1. Buttercup-Middleware - Integration Bus  (no deps)   -> capture _key_bus
2. Buttercup-Middleware - Message Queue    (no deps)   -> capture _key_queue
3. Buttercup-Middleware                    (deps: bus, queue)
4. Buttercup-Fulfilment - JBoss            (no deps)   -> capture _key_jb
5. Buttercup-Fulfilment                    (deps: jb)
6. ... (other perimeters same way)
7. Acme                                    (deps: Buttercup-Middleware, Buttercup-Fulfilment, ...)
```

This avoids the second-pass-to-wire pattern (which works but doubles your API calls and the failure surface).

## CRUD payload shapes

### Minimum viable service create

```json
{
  "title": "Buttercup-Middleware - Integration Bus",
  "description": "Integration bus engine health and throughput.",
  "enabled": 1,
  "sec_grp": "default_itsi_security_group"
}
```

POST to `/servicesNS/nobody/SA-ITOA/itoa_interface/service`. Response body is the new object with `_key` populated. Capture that.

| Field | Notes |
|---|---|
| `title` | Must be unique within `sec_grp`. Don't include the `_key` — let ITSI generate it. |
| `description` | Free text. Shown in the topology hover. Keep it short and operational. |
| `enabled` | 1 = monitored, 0 = paused. Default to 1 unless you have a reason. |
| `sec_grp` | `default_itsi_security_group` for global; otherwise the team's KV key. Get from `/itoa_interface/team`. |

### Service with dependencies

```json
{
  "title": "Buttercup-Middleware",
  "description": "Middleware perimeter rollup.",
  "enabled": 1,
  "sec_grp": "default_itsi_security_group",
  "services_depends_on": [
    {
      "serviceid": "<_key of Buttercup-Middleware - Integration Bus>",
      "kpis_depending_on": ["SHKPI-<_key of Buttercup-Middleware - Integration Bus>"]
    },
    {
      "serviceid": "<_key of Buttercup-Middleware - Message Queue>",
      "kpis_depending_on": ["SHKPI-<_key of Buttercup-Middleware - Message Queue>"]
    }
  ]
}
```

The `kpis_depending_on` array is what makes the dependency a *health* dependency (rolls up the child's service health into the parent's overall health). Without that array, ITSI records the dep but health doesn't propagate — the parent stays gray. Use it every time unless you specifically want a non-health dep.

### The SHKPI naming convention

Every ITSI service has an implicit, auto-created KPI called the Service Health KPI. Its `_key` is always:

```
SHKPI-<service _key>
```

You don't create it explicitly. It just exists. So if you have a service with `_key = abc123def456`, its SHKPI key is `SHKPI-abc123def456` and that's what you put in `kpis_depending_on`. There's no API call to "look it up" — it's a string concat.

### Partial update (rename without losing other fields)

The cutover from `SANDBOX-Buttercup-Middleware` to `Buttercup-Middleware` is a single field change. The full-object POST works but is risky — you have to re-send every field exactly or you'll wipe one out. Use partial update instead:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Buttercup-Middleware"}' \
  "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service/<_key>?is_partial_data=1"
```

The `?is_partial_data=1` query string flips the endpoint from "replace this object" to "merge these fields". Only the fields in your body are touched; everything else (deps, KPIs, entity rules, security) is left alone.

### Append a dependency without losing existing ones

Same partial-update pattern, but you must read-modify-write the `services_depends_on` array (there's no append primitive):

```bash
# 1. Read current deps
EXISTING=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service/<_key>?output_mode=json" \
  | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin).get('services_depends_on') or []))")

# 2. Append the new dep in Python (preserves shape)
NEW=$(python3 -c "
import json
existing = json.loads('$EXISTING')
existing.append({'serviceid':'<NEW_TARGET_KEY>','kpis_depending_on':['SHKPI-<NEW_TARGET_KEY>']})
print(json.dumps({'services_depends_on': existing}))
")

# 3. POST with is_partial_data=1
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$NEW" "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service/<_key>?is_partial_data=1"
```

### Delete

```
DELETE /servicesNS/nobody/SA-ITOA/itoa_interface/service/<_key>
```

Returns `HTTP 204 No Content` on success. Irreversible — no soft-delete, no recycle bin. Confirm bidirectionally before deleting anything you didn't create:

```bash
# Is anything depending on this service?
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service/<_key>?output_mode=json" \
  | python3 -c "import sys,json;s=json.load(sys.stdin);print('upstream:', len(s.get('services_depending_on_me') or []))"
```

## In-place rename vs delete-and-recreate

When cutting over from sandbox names to final names, **rename in place** with partial update. Never delete-and-recreate. Reasons:

- `_key` is preserved → any downstream dep that points at your service still works
- KPI history (if you had any KPIs running during phase 1) is preserved
- Audit trail in the kvstore stays continuous
- No race window where the dependency target doesn't exist

The only time you'd delete-and-recreate is if the service's `sec_grp` (team ownership) needs to change — that field isn't editable. Even then, do it one-at-a-time with depending services repointed first.

## Verification patterns

After phase 1 build:

```bash
# Count sandbox-prefixed services + report dep counts
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/SA-ITOA/itoa_interface/service?count=300&fields=title,_key,services_depends_on,services_depending_on_me&output_mode=json" \
| python3 -c "
import sys,json
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get('entry', [])
prefix = 'SANDBOX-CURSOR-'
sandbox = [s for s in items if s.get('title','').startswith(prefix)]
print(f'{len(sandbox)} sandbox services')
for s in sorted(sandbox, key=lambda x:x['title']):
    down = len(s.get('services_depends_on') or [])
    up   = len(s.get('services_depending_on_me') or [])
    print(f'  {s[\"title\"]:50s} down={down} up={up}')
"
```

What "good" looks like (for a 16-node tree with 1 parent + 5 perimeter rollups + 10 leaves):
- Leaves: `down=0`, `up=1` (their perimeter)
- Perimeter rollups: `down=N` (their leaves), `up=1` (the program parent)
- Program parent: `down=5`, `up=0`

Any leaf with `up=0` is an orphan. Any rollup with `up=0` is missing from the program parent. Any leaf with `down>0` is suspicious (leaves shouldn't have deps in this model).

After phase 3 cutover, re-run with the new prefix being "" (i.e., the final names) and verify:
- No more `SANDBOX-CURSOR-` titles exist (stray cleanup)
- Cross-team deps are present where expected (and only where expected)

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Building directly without sandbox prefix | One typo and you've polluted production names. Cleanup is dozens of one-off deletes | Always sandbox-prefix phase 1, even if you're "sure" |
| Treating `SANDBOX-` as actually isolated | It's still in the same kvstore, same `sec_grp`, same KPI search load | Use the prefix as a label, not as protection. Apply normal change-control to anything that does actual searches |
| Pointing dependencies at services owned by other consultants without coordinating | They refactor → your tree breaks; or they see ghost services in their topology | Always inform owners before cross-team deps; document in the project tracker |
| Modifying services owned by other consultants (POST to their `_key`) | Overwrites their work; no undo | Strict rule: your tree depends on theirs, never the reverse. POST only to your own keys |
| Using full POST (replace) for a title rename | Strips deps, KPIs, entity rules if you forget to re-include them | Always use `?is_partial_data=1` for field-level edits |
| Creating services in title-alphabetical order (top-down) | First service has dep on second; second doesn't exist yet → 400 or silent missing dep | Leaves-first ordering, derived from the dep graph, not the alphabet |
| Hardcoding `_key` values in scripts | Keys are environment-specific UUIDs; script becomes unportable | Look up keys by `title` at runtime; cache to a JSON file for the session |
| Skipping `kpis_depending_on` in the dep array | Dep exists but health doesn't propagate; parent service stays gray forever | Always include `SHKPI-<child_key>` in the array |
| Trusting the default `count=30` page on `/itoa_interface/service` | You'll think a service is missing when it's just past page 1 | Pass `count=300` (or higher) when discovering. Add explicit pagination if you have >300 services |
| Deleting + recreating to change a service's title | Breaks every downstream dep; loses history | `?is_partial_data=1` rename in place |
| Using the Service Topology view to "fix" things during phase 1 | Manual UI edits don't get captured in your build script → can't reproduce the tree | All changes via script in phase 1; UI is read-only review tool until phase 3 done |

## Related skills

- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities, troubleshooting (prerequisite for this skill)
- `splunk-itsi-entity-cmdb-lookup` — the upstream that drives Layer-2 entity rules on the Platform leaves
- `splunk-itsi-entity-binding-architecture` — the 4-layer chain that scopes Platform KPIs to the right hosts per leaf
- `splunk-itsi-kpi-creation-via-api` — how to bulk-provision the 6 OS KPIs across all Platform leaves
- `splunk-itsi-content-pack-creation` — overlay strategy for the content pack that feeds the Platform pillar
- `otel-vs-splunk-ingestion` — what's feeding the KPIs that hang off the leaves
