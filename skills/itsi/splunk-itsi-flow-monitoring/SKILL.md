---
name: splunk-itsi-flow-monitoring
category: itsi
description: Model a multi-step transaction / process / integration flow in Splunk ITSI so each step becomes a service with KPIs, enabling bottleneck detection and step-latency trending — something ITSI cannot do out of the box. Covers the core idea (build the flow logic in SPL, then map each step/stage/lane to a service and roll them up into an end-to-end service with business-outcome KPIs), the two entity strategies (real entities per named lane with a shared info-tag rollup, vs. pseudo-entities split by a per-transaction correlation key), the standard per-step KPI trio (item count, completion/transit time by correlation key, success/rejection rate), the E2E business-outcome KPIs (cycle-time P95, SLA-breach %, exceptions-per-N, straight-through rate), how to operationalize bottleneck detection via graded step thresholds + health rollup and step-latency trending via the metrics index, the one-shared-base-search performance rule, and the flow-specific failure modes (only SHKPI rows in itsi_summary because match_entities yields null serviceid before membership resolves). Use when the user wants transaction/process/flow monitoring, step/stage/funnel modeling, bottleneck or cycle-time detection, end-to-end latency across a pipeline, or asks how to turn a correlated event flow into ITSI services and KPIs.
disable-model-invocation: true
---

# ITSI Flow Monitoring (transaction / process / pipeline)

ITSI has **no native concept of a flow**. It monitors services and KPIs, not transactions that move
through steps. But if you can express the flow logic in **SPL** — correlate events into steps and
compute per-step volume / timing / outcome — you can map each step to a **service with KPIs**, roll
them into an **end-to-end (E2E) service**, and operationalize **bottleneck detection** and
**step-latency trending**. This skill is the reusable pattern for doing that.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use

- The user wants to monitor a transaction / process / integration flow (order-to-cash,
  ingest→transform→publish, request→process→respond, submit→approve→settle, any multi-hop pipeline).
- They ask "where is the bottleneck", "how long does the whole thing take", "which step is slow",
  "cycle time", "aging", "stuck items", "straight-through / touchless rate", "SLA breach".
- Events for each step already land in Splunk and share a correlation key (or per-lane identifier).
- They want step-over-step trending, not just a single aggregate.

## Prerequisite: the flow logic must be expressible in SPL

You need one of:
- **A correlation key** shared across step events (e.g. a transaction/order/message id) so a single
  SPL `stats ... by <key>` can reconstruct each item's journey and per-step timestamps, **or**
- **A per-lane/stage identifier** on each event (e.g. an interface or stage code) so
  `stats ... by <lane>` yields per-lane throughput/latency/errors.

If neither exists, flow monitoring isn't possible yet — fix the instrumentation first.

## The model

```
                          ONE shared base search  (all step/lane metrics in one SPL)
                                        │  (one generated indicator search)
     ┌───────────────┬─────────────────┼───────────────────┬─────────────────────────┐
   Step/Lane 1     Step/Lane 2      Step/Lane 3   ...      Step/Lane N        E2E rollup service
   (service+KPIs)  (service+KPIs)   (service+KPIs)         (service+KPIs)     (business-outcome KPIs)
        └────────────────┴────────────── children of ──────────────┴──────────────► E2E service
```

- **One service per step/stage/lane.** Its KPIs describe that step in isolation.
- **One E2E rollup service** as parent, carrying whole-journey **business-outcome** KPIs. Its health
  rolls up from the step services, so a slow/failing step visibly degrades the E2E flow.
- Attach the E2E service under the relevant perimeter/pillar in the service tree (see
  `splunk-itsi-service-tree-design`).

## Two entity strategies (pick per flow)

### A. Named lanes → real entities + shared-tag rollup
Use when the flow has a **small, fixed set of named lanes/stages** (interfaces, queues, named
process steps). Create one **real entity per lane**, each carrying:
- an alias/identifier field = the lane id (`lane`, `stage`, `interface`…) → each **step service**
  scopes on `<laneField> matches "<lane>"` with `is_service_entity_filter=true`;
- a shared **info tag** (e.g. `flow_role=member`) → the **E2E service** scopes on
  `flow_role matches "member"` so it aggregates **all** lanes with no hard-coded list (add a lane
  later, tag it, it joins automatically).

Each lane entity then belongs to **two** services (its step + the E2E rollup) — the `services=2`
count is your membership-resolution check. Full mechanics + failure table:
`splunk-itsi-entity-binding-architecture` (see its multi-service worked example).

### B. Per-transaction correlation key → pseudo-entities
Use when items are **high-cardinality per-transaction** (orders, invoices, messages). Don't create
entity-store objects. Split by the correlation key:
`is_entity_breakdown=true`, `entity_breakdown_id_fields=<TXN_ID>`, `is_service_entity_filter=false`.
Each item becomes a per-entity row you can grade individually (e.g. flag the specific stuck items).
Beware the Episode Review flood with graded thresholds on high cardinality — see Bottleneck
detection below and the dedicated section in `splunk-itsi-entity-binding-architecture`.

You can mix: step **count/latency** KPIs use pseudo-entities (per-item), while step **rate** KPIs
are aggregate-only.

## Per-step KPI trio

For each step service, aim for two or three KPIs:

| KPI | Aggregation | Breakdown | Unit / naming |
|---|---|---|---|
| **Item count at this step** (volume/throughput) | `count` | none (`is_entity_breakdown=false`) — inherently safe | blank unit; put `(count)` in the KPI name |
| **Completion / transit time into this step** | `perc95` or `avg` of per-item latency | **by correlation key** (pseudo-entity) so each item is individually gradeable | native time unit (`s` or `min`) |
| **Success / rejection rate** | `avg` of a 0/100 flag, or `100*errors/total` | aggregate-only (a rate can't be meaningfully split per item) | `%`; describe in the name |

Notes:
- ITSI restricts units to a controlled list; for domain counts leave the unit blank and encode the
  meaning in the **KPI name** (`… (count)`, `… (min, by item)`). See `splunk-itsi-kpi-creation-via-api`.
- Compute latency as `stept_end - step_prev_end` per item so it's a fixed, stable value (avoids the
  moving-window "cliff" where items age out of the search window and flap).

## E2E rollup: business-outcome KPIs

On the E2E service, measure the **whole journey**, not any single step:

- **Cycle time P95** (first step → final step), unit `min` — the headline "how long does it take".
- **SLA breach %** — share of items whose cycle time exceeds a target.
- **Exceptions per N items** (e.g. per 100) — normalized error pressure across the flow.
- **Straight-through / touchless rate %** — share of items that completed with no error/rework step.
- **Total completed volume** (count) — flow throughput.

These give leadership-level signal; the step KPIs give the operational "where".

## Operationalize bottleneck detection

1. **Graded thresholds on the slow dimension.** Put a graded threshold on the **per-item completion
   time** KPI of the step you want to police (e.g. critical `>= X min`). Those items go critical →
   the step service health drops → it rolls up into the E2E health. Keep the other steps' entity
   thresholds **flat** so the degraded step is isolated and obvious.
2. **Keep Event Analytics calm.** Graded **entity** thresholds on high-cardinality pseudo-entities
   trip the always-on `Service Monitoring - Entity Degraded` correlation search → notable/episode
   flood. Options: keep entity thresholds flat until you deliberately want episodes; grade only a
   tight critical band that catches a handful of items; or use a scoped Notable Event Aggregation
   Policy. Details + cleanup: `splunk-itsi-entity-binding-architecture` (pseudo-entity flood section).
3. **Display-only amber.** To show a degraded tile without generating episodes, set the graded
   threshold but `aggregate_thresholds_alert_enabled=false`.

## Operationalize trending

Each step's count and latency are written to the metrics index (`itsi_summary_metrics`) every cycle.
Comparing step-latency series over time reveals the **moving** bottleneck (which step's P95 is
climbing) and volume funnel drop-off (where items are lost). The Service Analyzer KPI trend flip and
Deep Dive lanes read this automatically.

Caveat: an individual **pseudo-entity's** per-entity history is legitimately sparse (items appear
and clear), so drilling one stale item shows "no data / Backfill" even on a healthy pipeline — that's
expected, not a gap. See `splunk-itsi-common-errors` §5.

## Build workflow

```
- [ ] 1. Confirm the flow logic is expressible in SPL (correlation key or lane id present).
- [ ] 2. Write ONE shared base search that emits per-step/per-lane metrics in a single pass.
- [ ] 3. Choose entity strategy A (real entities + shared tag) or B (pseudo-entities by key).
- [ ] 4. Create one service per step + one E2E rollup; wire E2E as parent, attach under the pillar.
- [ ] 5. Add the per-step KPI trio + the E2E business-outcome KPIs (flat thresholds first).
- [ ] 6. For strategy A: confirm each entity's `services` count resolved before trusting output.
- [ ] 7. Wait for a SCHEDULED indicator run; verify itsi_summary by itsi_service_id (not source=).
- [ ] 8. Turn on graded thresholds only where you want bottleneck signal; keep the rest flat.
- [ ] 9. (Optional) Add a flow tab to the glass table and a per-item investigation drilldown.
```

## Performance rule (do not skip)

**One shared base search per flow**, feeding all step + E2E KPIs, on a sane `alert_period`
(match it to the analysis window — e.g. 30 min for a 24h flow view). Do **not** create a base search
per step/lane unless step populations genuinely differ and you need clean per-step counts — even then
keep it to a handful. N steps × M metrics separate searches is the classic concurrency-killer
(`splunk-itsi-performance-tuning`, and the "no data / Backfill" concurrency story in
`splunk-itsi-common-errors` §5).

## Flow-specific failure modes

| Symptom | Cause | Fix |
|---|---|---|
| **Only `SHKPI-*` rows in `itsi_summary`, zero real KPI rows** | Indicator derives `serviceid` from `match_entities(<alias>)` → `mvexpand`; membership not resolved when it was generated ⇒ `serviceid=null` ⇒ rows dropped | Confirm entity `services` count > 0, re-save the **base search** (full-object POST) to regenerate the indicator, wait for the next **scheduled** run |
| `itsi_summary` query returns 0 rows | Filtered on `source="*<BS>*"` | Query by `itsi_service_id IN (...)` / `itsi_kpi_id` — that's how rows are keyed |
| Manual dispatch returns 201 but no KPI rows appear | ITSI indicator write action needs scheduler context; manual dispatch is unreliable | Wait for the scheduled run (or re-save + wait). See `splunk-itsi-kpi-creation-via-api` |
| Step latency KPI flaps in/out of critical | Latency computed against a moving window edge (item ages past `earliest`) | Compute latency as a fixed per-item delta (`end - prev_end`), not "now - start" |
| E2E health green while a step is clearly slow | Step's degraded severity isn't grading (flat threshold) or step service isn't a child of E2E | Grade the step's per-item KPI; verify tree parentage |
| Rate KPI shows blank / weird per-entity values | A rate was split by the correlation key | Make rate KPIs aggregate-only (`is_entity_breakdown=false`) |

## Anti-patterns

| Anti-pattern | Why it's bad | Do instead |
|---|---|---|
| One base search per step/lane | N×M scheduled searches, concurrency saturation | One shared base search per flow |
| Grading every per-item threshold at once | Episode Review flood from `Entity Degraded` | Grade only the step under investigation; flat elsewhere |
| Encoding the flow in the service tree but computing nothing per step | Pretty tree, no signal | Every step service needs the KPI trio |
| Splitting a rate/percentage by the correlation key | Meaningless per-item rates | Rates aggregate-only; counts/latency by item |
| Hard-coding the lane list in the E2E rule | Breaks when a lane is added | Shared info tag the E2E rule matches |

## Related skills

- `splunk-itsi-entity-binding-architecture` — the 4-layer scoping chain, the multi-service flow
  worked example, and the pseudo-entity Episode Review flood + cleanup
- `splunk-itsi-kpi-creation-via-api` — KPI payload shapes, thresholds for health scores, units,
  indicator dispatch vs. scheduled-run behavior, the read-modify-write pattern
- `splunk-itsi-service-tree-design` — where the E2E rollup and step services sit in the tree
- `splunk-itsi-performance-tuning` — base-search `alert_period`, staggering cron, concurrency
- `splunk-itsi-common-errors` — §5 "no data / Backfill" (metrics-index gaps, pseudo-entity sparseness)
- `splunk-itsi-glass-table-rest` — building a flow tab of step-health tiles
- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities (prereq)
