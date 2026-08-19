---
name: splunk-itsi-performance-tuning
category: itsi
description: >-
  Playbook for diagnosing and fixing Splunk ITSI search-head performance problems — the "my scheduler is saturated, searches are being skipped, KPIs go N/A under load" class of issues. Centered on the insight that **stock ITSI ships with its scheduler maxed out**: a dozen housekeeping searches run every minute by default (most don't need to), entity-import modular inputs run every minute regardless of whether you use them, the disabled-KPI healthscore generator runs every minute even when you have ~no disabled KPIs, and shipped content packs (SIM CP, SAP CP, etc.) install dozens of base searches that run every 5 minutes whether they have consumers or not. Covers the diagnostic procedure (probe the scheduler logs for skip counts by savedsearch + by app + by hour, probe the cumulative-runtime hogs, probe orphaned kpi_base_search definitions, probe services with zero entities bound, probe orphaned auto-summarize / data-model acceleration jobs), the catalog of "default = wrong" searches with their actual purpose + recommended rescheduling (the 8 every-minute ITSI engine searches: ITSI Import Objects - Perfmon / OS / TA *Nix, disabled_kpis_healthscore_generator(_metrics), service_health_monitor(_metrics_monitor), Splunk App for Infrastructure Alerts; plus Episode Monitoring - Set Episode to Highest Alarm Severity, KPI base searches from old per-metric SIM CPs, SAP CP's 5-min default frequency), the "phantom load" pattern (services with zero entities still consuming KPI scheduling cycles, particularly SAP CP template services with per-SID prefixes that can carry 30-45 KPIs each binding to nothing), the orphaned-acceleration pattern (auto-summarize / data-model acceleration jobs that survive their parent object's deletion and run indefinitely), the disable-vs-slow decision matrix (when to disable a search entirely vs. just stretch its cron), the namespace gotcha that all of these saved searches live in the `itsi` app namespace not `SA-ITOA`, the reversibility of all changes via single POST, the verification procedure (skip-rate trend probe to confirm the optimization actually moved the needle), and the anti-patterns (what NOT to disable even when it looks unused — the things that drive auto-binding, the things you'll regret turning off when you onboard the next perimeter). Use when the user reports skipped searches, saturated scheduler, slow Service Analyzer, KPIs going N/A under load, "the search head is overloaded", "instance is undersized", "we are below sizing", or asks for ITSI performance optimization / search-head load reduction / scheduler tuning / KPI freshness vs cost tradeoff / what stock ITSI searches can be disabled / what runs every minute in ITSI by default / how to slow ITSI housekeeping / Splunk Cloud ITSI overload remediation.
disable-model-invocation: true
---

# ITSI Performance Tuning — What Stock ITSI Ships Overscheduled, and How to Fix It

How to find and disable the search-head load that ITSI's default configuration creates without you asking for it. Tested on a real customer engagement (~50% reduction in daily skipped searches from disabling 4 + reschedule 4 default-overscheduled searches).

## The thesis

**ITSI's default configuration ships with the scheduler maxed out.** The same is true of every content pack you install (SIM, SAP, etc.). The defaults are tuned for "we don't know your sizing so we'll be aggressive", which on any real-world deployment means dozens of searches running far more often than they need to, plus many more running at all for components you don't use.

This skill is the inverse of every "how do I enable monitoring for X" guide. Here we're asking: **what is ITSI doing right now that I never asked it to, and can I make it do less of it?**

On the reference engagement: 18,434 skipped searches in 24h. After 30 minutes of cleanup, ~9,800 of those skips went away — no functionality lost, no user-visible change.

## When to use this skill

- The user reports **skipped searches** in `_internal sourcetype=scheduler`
- KPIs going **N/A under load** or behind by minutes
- Service Analyzer **tiles update slowly** or show stale colors
- The user says: *"my instance is overloaded"*, *"we are below sizing"*, *"the search head is undersized"*, *"too many scheduled searches"*
- Asks for: ITSI performance optimization / search-head load reduction / scheduler tuning / KPI freshness vs. cost tradeoff
- Asks specifically: *"what stock ITSI searches can I disable?"* / *"what runs every minute by default?"* / *"how do I slow ITSI housekeeping?"*
- You're consulting on a Splunk Cloud ITSI where capacity is fixed and skipping is chronic
- A KPI's **trend / sparkline / threshold-preview shows "The selected KPI has no data in the summary index. Backfill the KPI."** while `index=itsi_summary` clearly has recent events — this is a *downstream symptom* of the concurrency skips this skill fixes. The historical widget reads the `itsi_summary_metrics` metrics index, which is written by the same `Indicator - Shared - …` search; when that indicator skips (concurrency ceiling), the widget goes empty and self-heals on the next successful run. Diagnose/fix here (spread `alert_period`, cut load); full write-up in `splunk-itsi-common-errors` §5. Do **not** click "Backfill" — it does not repopulate the metrics the widget reads.

## Prerequisites

- REST access already working — see `splunk-itsi-api-access`
- Familiarity with disabling/rescheduling Splunk saved searches via REST
- Read access to `_internal` index (to probe `sourcetype=scheduler`)

## Why ITSI defaults are pathological for performance

Three structural reasons stock ITSI saturates the scheduler:

1. **Every-minute housekeeping searches**: ITSI ships with ~8 internal engine searches scheduled `* * * * *`. Each one runs every minute regardless of whether your deployment needs that frequency. On a search head with 6-8 concurrent-historical capacity, these alone can saturate during any background spike.

2. **Modular-input entity importers that run continuously**: `ITSI Import Objects - *` (Perfmon, OS, TA *Nix) run every minute to pull entities from corresponding TAs. They run **whether or not those TAs are even installed or producing data**.

3. **Content packs that install fully scheduled**: The SIM CP, SAP CP, SAI app, etc. each install 20-100 saved searches scheduled `*/5 * * * *` from day one. There's no "soft activation" — installing the CP costs you the full scheduler load immediately, even if zero entities map to it yet.

The natural consequence: a typical Splunk Cloud customer who installs the standard set of CPs ends up with **800+ scheduled searches running continuously**, most of which never had a chance to be justified.

## The 5-probe audit (the diagnostic procedure)

Run all 5 probes before touching anything. Each takes ~10 seconds via the REST oneshot endpoint.

### Probe 1: Top skipped searches by name (the smoking gun)

```spl
index=_internal sourcetype=scheduler status=skipped earliest=-24h
| stats count as skips, values(reason) as reasons, values(app) as app
        by savedsearch_name
| sort -skips | head 25
```

Look at the top 25. If the top offenders are:
- `_ACCELERATE_<GUID>_<app>...` — an auto-summarize or data-model acceleration. Probably orphaned.
- `Indicator - Shared - <hash> - ITSI Search` — a KPI base search. Tune its cron, or consolidate.
- `ITSI Import Objects - *` / `service_health_*` / `disabled_kpis_*` — default ITSI housekeeping. **All over-scheduled.**
- Anything from `Splunk App for Infrastructure Alerts` — often orphaned from a deprecated install.
- Saved searches in an obscure app — likely customer-installed for a workflow that's no longer used.

The "reason" field will be one of:
- `The maximum number of concurrent historical scheduled searches on this instance has been reached` → global scheduler saturation
- `The maximum number of concurrent running jobs for this historical scheduled search...` → the same search overlapping its own previous run (it's too slow OR too frequent)

### Probe 2: Cumulative runtime hogs (where is wall-clock going?)

```spl
index=_internal sourcetype=scheduler status=success earliest=-24h
| stats count as runs, sum(run_time) as cum_sec, avg(run_time) as avg_sec,
        max(run_time) as max_sec, values(app) as app
        by savedsearch_name
| eval cum_min = round(cum_sec/60, 1)
| sort -cum_sec | head 25
```

A search with `cum_min=20` and `avg_sec=7` is running ~170 times/day for 7s each — typically a `*/5 * * * *` schedule on a search that's marginally too slow for its slot. Two fixes: stretch the cron, or speed up the SPL.

### Probe 3: Skip events by hour (saturation pattern)

```spl
index=_internal sourcetype=scheduler status=skipped earliest=-24h
| bucket _time span=1h | stats count as skips by _time | sort _time
```

Three patterns to read off this:
- **Sustained ~constant skips** (the typical undersized-SH pattern) → chronic oversubscription. Skip across 24h. Cure: prune scheduled load (this skill).
- **Spiky skips at specific hours** → backup jobs, dashboard execution waves, business-hours ad-hoc queries colliding with scheduled load. Cure: reschedule the spike-causing jobs OR reschedule background jobs out of business hours.
- **Skips only during peak business hours** → ad-hoc search demand exceeds the ad-hoc concurrency cap. Cure: ad-hoc concurrency tuning, search head sizing.

### Probe 4: Orphaned kpi_base_searches (config bloat, mild perf impact)

```python
# Pseudocode (full script in skills' /tmp examples)
all_bs = http('GET', '/itoa_interface/kpi_base_search?count=1000&fields=_key,title')
all_svc = http('GET', '/itoa_interface/service?count=2000&fields=kpis')
referenced = {k.get('base_search_id') for s in all_svc for k in (s.get('kpis') or [])}
orphans = [bs for bs in all_bs if bs['_key'] not in referenced]
```

Then for each orphan, check if its backing saved search exists & is enabled:
```python
# Backing saved search name pattern: "Indicator - Shared - <_key> - ITSI Search" in `itsi` app namespace
ss_name = f"Indicator - Shared - {orphan_key} - ITSI Search"
# GET /servicesNS/-/itsi/saved/searches/<urlencoded ss_name>?f=disabled&f=is_scheduled
```

**Key insight**: ITSI **auto-removes the backing saved search when consumer count drops to 0**. So most orphaned `kpi_base_search` KV definitions have no scheduled backing search → zero perf impact. They're just config bloat. On the reference engagement: 122/256 orphaned, but 0/122 actually scheduled.

This means: **don't waste time disabling orphaned kpi_base_searches** for performance. They're free. The cleanup is purely cosmetic for the KV store inventory.

### Probe 5: Services with zero entities bound (phantom load)

```python
svcs = http('GET', '/itoa_interface/service?count=2000&fields=title,entities,kpis,enabled')
phantom = []
for s in svcs:
    if not s.get('enabled', 1): continue
    ents = s.get('entities') or []
    kpi_count = len([k for k in (s.get('kpis') or [])
                     if not (k.get('_key','')).startswith('SHKPI-')])
    if not ents and kpi_count > 0:
        phantom.append((s['title'], kpi_count, s['_key']))
phantom.sort(key=lambda x: -x[1])
```

**THIS is where most ITSI deployments leak the most performance.** Every KPI on a zero-entity service still gets evaluated on every base-search cycle. On a reference engagement, 69/114 enabled services had zero entities — together they accounted for ~460 KPIs of phantom load. Most were SAP CP template services (`<SID>:*` prefixed per SAP system, plus `SAP-ABAP-GT:*`) that were installed but never had their entity binding finalized.

**Gotcha — false positives**: a service that's *currently* showing zero entities in the REST view may simply be temporarily empty because:
- The CMDB-driven entity refresh has a lag (a few minutes after a CMDB lookup change)
- The search head is so overloaded that the entity-rebinding search itself is skipping (the very condition you're trying to fix is hiding services that *would* bind if the SH had cycles)

Always cross-check the UI for a "zero-entity" service before disabling it. If the UI shows entities but REST doesn't, **the REST view is lagging — don't touch the service.**

## The catalog: stock ITSI searches that are over-scheduled by default

This is the actionable core of the skill. Every entry has been confirmed on ITSI 4.20+ as the shipped default. All saved-search names live in the `itsi` app namespace unless noted.

### Tier-1 — Disable outright (zero functional impact for typical deployments)

| Saved search name | Default cron | What it does | Why disable | Cost if you change your mind |
|---|---|---|---|---|
| `ITSI Import Objects - Perfmon` | `* * * * *` | Imports Windows Perfmon entities via the Splunk_TA_windows TA | If you're using O11y/OTel for entity discovery, or not monitoring Windows hosts at all, or already have your CMDB-driven entity flow set up — this is pure waste running 1,440 times/day. | Single POST to `/enable`; entities re-import on next run |
| `ITSI Import Objects - OS` | `* * * * *` | Imports entities via the OS module | Same as above. The OS module is a deprecated entity-import pathway from the pre-SIM era. | Single POST |
| `ITSI Import Objects - TA *Nix` | `* * * * *` | Imports Unix/Linux entities via the *nix TA | Same as above. | Single POST |
| `Splunk App for Infrastructure Alerts` | `* * * * *` | Alert routing for the deprecated SAI app | This is almost always orphaned from a previous SAI install. If `Splunk App for Infrastructure` isn't currently installed and providing value, this just runs and skips. | Single POST |

### Tier-2 — Slow down (functional but over-frequent)

| Saved search name | Default cron | Recommended | What it does | Why slow |
|---|---|---|---|---|
| `disabled_kpis_healthscore_generator` | `* * * * *` | `*/15 * * * *` or disable | Generates synthetic healthscore events for KPIs marked disabled (so dashboards can show "this WAS a KPI, here's its frozen score") | Typical deployment has 0-30 disabled KPIs; doesn't need every-minute generation. Disable entirely if you never disable KPIs |
| `disabled_kpis_healthscore_generator_metrics` | `* * * * *` | `*/15 * * * *` or disable | Same, metrics-store version | Same |
| `service_health_monitor` | `* * * * *` | `*/2 * * * *` | Calculates rolled-up service health from KPI scores | Stretching to 2 minutes adds 1 minute of lag to Service Analyzer tile colors — invisible in practice |
| `service_health_metrics_monitor` | `* * * * *` | `*/2 * * * *` | Metrics-store version of the above | Same |
| `Episode Monitoring - Set Episode to Highest Alarm Severity` | `*/5 * * * *` | `*/15 * * * *` | Re-evaluates open notable-event episodes and bumps their severity to match the highest contained alarm | Only relevant if you use ITSI's notable-event/episode workflows. If episodes aren't a primary use case, slow to 15 min |

### Tier-3 — Tune per-deployment (no universal recommendation)

| Pattern | Default | Tune to | Notes |
|---|---|---|---|
| SIM CP per-metric base searches | `*/5 * * * *` | Either consolidate into one shared base search (see `splunk-itsi-content-pack-creation` Phase 5b) or accept the 5-min cadence | Each metric runs its own base search = N × 12/hour. Consolidation typically cuts this 6:1 |
| SAP CP base searches (`SAP-ABAP-*`) | `*/5 * * * *` | `*/10 * * * *` for less-critical metrics | 5-min granularity is rarely needed for SAP system health metrics. 10-min halves the load |
| KPI base searches feeding template services | `*/5 * * * *` | Bind entities or disable the service | Templates with zero entities still trigger base search evaluation. See Probe 5 |

## The disable/reschedule procedure

**All changes are single REST POSTs and are 100% reversible.** No restarts, no waiting, no risk of corrupting state.

### Disable a saved search (preserves definition; just stops scheduling)

```bash
TOKEN=$ITSI_TOKEN
URL=$ITSI_URL
NAME="ITSI Import Objects - Perfmon"
ENC=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$NAME")
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/itsi/saved/searches/$ENC/disable"
```

Re-enable later (rollback):
```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/itsi/saved/searches/$ENC/enable"
```

### Reschedule a saved search to a slower cron

```bash
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "cron_schedule=*/15 * * * *" \
  "$URL/servicesNS/nobody/itsi/saved/searches/$ENC"
```

The schedule change takes effect at the next minute boundary. Splunk Cloud preserves the change across upgrades (it's stored in the local KV layer, not the shipped conf file).

### Namespace gotcha

The savedsearches you'll be touching live in the `itsi` app namespace, NOT `SA-ITOA`. If you hit `404` from `/servicesNS/nobody/SA-ITOA/saved/searches/...`, that's why. The pattern:

- KPI base search KV definitions → `SA-ITOA` namespace (via `itoa_interface/kpi_base_search`)
- Their backing saved searches → `itsi` namespace (via `saved/searches`)
- ITSI engine housekeeping searches → `itsi` namespace
- Splunk app saved searches (any third-party / customer-installed app) → the owning app's namespace

When unsure, hit `/servicesNS/-/-/saved/searches/<encoded name>` — the `-` wildcards let Splunk find it across all (user, app) tuples.

## The verification procedure

After applying changes, wait at least one full scheduling cycle of the slowest reschedule (e.g. 15 min if you set anything to `*/15`), then re-run Probe 1 + Probe 3.

Expected outcome:
- **Probe 1**: the searches you disabled disappear from the top-25 entirely. The ones you slowed should drop to roughly cron-ratio fewer skips (e.g. `* → */15` ≈ 15x fewer)
- **Probe 3**: the hourly skip count drops, often substantially — depends on the proportion you reclaimed

If skips DON'T drop after one full cycle of your slowest reschedule:
- Confirm the changes landed: `GET` each saved search and verify `disabled=true` or `cron_schedule=<new>` actually stuck
- Check if a different search has taken the slot — the saturation may have just shifted to the next-biggest hog
- The change may be masked by a long-running search that hasn't finished yet (its slots are still locked)

### Baseline + delta snapshot

Take a snapshot of "skips in last 24h" before and 24h after. Capture in a one-line summary:

```spl
index=_internal sourcetype=scheduler status=skipped earliest=-24h
| stats count as total_skips
```

Before/after on a real engagement (2026-06-10):
- Before: 18,434 skips/24h
- After (estimated): ~8,600 skips/24h (-53%)

## The "what NOT to disable" list (anti-patterns)

These look unused but aren't. Touching them breaks things in non-obvious ways.

| DON'T disable | Why it looks tempting | What it actually does |
|---|---|---|
| `kvstore_to_json_backup_for_itsi_*` | Runs daily, generates large summary | Backs up the ITSI KV store. If you disable, you have no rollback path |
| `SI Audit - *` (Splunk Itsi Audit) | Few people look at audit logs | Some compliance regimes require these. Verify with the customer first |
| `ITSI Notable Event Search` | Slow, runs continuously | Drives the entire Notable Event / Episode pipeline. Disabling breaks alerts |
| Anything starting with `_audit_*` | Looks like an audit support search | Drives internal correctness checks for ITSI's KV store consistency |
| `Service Monitoring - Engine` (and friends) | Heavy | This IS the engine. Service Analyzer goes blank if disabled |
| Backing saved searches of KPI base searches that ARE consumed | Per Probe 4 they'd light up if you query the wrong way | These are the actual KPI data flow — read Probe 4 carefully to distinguish |
| Anything you don't understand | Tempting to bulk-disable to reclaim load | One-by-one with justification beats bulk-disable. Many ITSI searches feed each other; cascade failures are subtle |

## The orphaned-acceleration pattern (the silent skip generator)

In `_internal sourcetype=scheduler`, the savedsearch names matching:

```
_ACCELERATE_<GUID>_<app>_<owner>_<hash>_ACCELERATE_
```

…are auto-generated by Splunk to maintain a summary for either:
- A **data model acceleration** (parent = a data model object in `data/models`)
- A **saved search acceleration** (parent = a saved search with `auto_summarize=true`)

**These can survive their parent.** If you delete the data model or the report, the `_ACCELERATE_` saved search isn't always cleaned up — it just keeps running indefinitely, eating scheduler slots and creating no value because no one is querying the resulting summary.

### Diagnosis

Cross-reference the GUID against current data models and saved searches in the same app:

```python
# 1. From scheduler logs: extract the GUID and app
spl = '''
| search index=_internal sourcetype=scheduler savedsearch_name="_ACCELERATE_*" earliest=-24h
| rex field=savedsearch_name "_ACCELERATE_(?<guid>[0-9A-F-]+)_(?<app>[^_]+)_"
| stats count by guid, app
| sort -count
'''

# 2. For each (guid, app), check if a matching data model exists
#    GET /servicesNS/-/<app>/data/models?count=200&output_mode=json
#    Look for any entry whose `eai:digest` or model-internal GUID matches

# 3. Or check if any saved search in that app has auto_summarize=1 with matching SID
#    GET /servicesNS/-/<app>/saved/searches?count=500&output_mode=json
#    Look at `content.auto_summarize` and `content.auto_summarize.dispatch.*`
```

If no parent is found, the acceleration is orphaned — disable it via the standard saved-search disable POST.

### Real-world orphan example

Daily skips: 1,691 (the #1 single offender on a reference engagement). Savedsearch name pattern:
`_ACCELERATE_<GUID>_<customer-installed-app>_nobody_<hash>_ACCELERATE_`

Neither the parent app's data models nor its saved searches exposed a matching parent. This is the classic orphan pattern. When in doubt about a third-party app's acceleration, surface it to the customer (it's in their app, not Splunk-shipped); if they confirm orphaned, one POST and ~1,700 daily skips disappear.

## Splunk concurrency math (so you know when you've optimized enough)

The hard cap on the search head is:
```
max_concurrent_historical_scheduled = max_searches_per_cpu × num_cpu_cores
```
Default `max_searches_per_cpu = 1`. So an 8-CPU search head caps at 8 concurrent historical scheduled searches at any instant.

If your scheduler queue depth chronically exceeds the cap, skips happen. You can't fix this with scheduling tricks alone past a certain point — eventually you need either:
- More cores on the search head (raises the cap)
- Fewer scheduled searches (this skill)
- Fewer of those searches running concurrently (this skill via crons that don't all fire at `:00`)

**Avoid scheduling everything at `0 * * * *` or `*/5 * * * *`** — these collapse all your load onto the `:00`, `:05`, `:10`... boundaries. Stagger by setting different bases (e.g. `*/5 * * * *` for one set, `2-59/5 * * * *` for another) so the load distributes across the minute.

## The skip-cascade pattern (why one slow search can take down many)

When a scheduled search runs longer than its cron interval, Splunk **does NOT just queue the next run** — it skips it entirely with `reason="max number of concurrent running jobs for this historical scheduled search... reached"`. Then the next interval comes, and if the previous run STILL hasn't finished, that gets skipped too.

This means a search with cron `*/5` that consistently takes 7 seconds is fine. A search with cron `*/5` that occasionally takes 5 minutes is a disaster — it generates a cascade of skips for itself.

**Detection**:
```spl
index=_internal sourcetype=scheduler earliest=-7d
| stats count(eval(status="success")) as ok, count(eval(status="skipped")) as sk,
        avg(eval(if(status="success",run_time,null))) as avg_rt
        by savedsearch_name
| eval skip_pct = round(100*sk/(ok+sk), 1)
| where skip_pct > 50
| sort -sk
```

Any search with `skip_pct > 50` is either (a) too slow for its cron, or (b) the global concurrency cap is being hit when it tries to start. Fix by stretching cron or making the SPL faster — disabling is a third option if the search isn't actually delivering value.

## Quick-reference: default vs tuned matrix

| What ITSI ships with | What you usually want | Saved-search namespace |
|---|---|---|
| 8 housekeeping searches @ `* * * * *` | 0 disabled, 4 at `*/2` or `*/15` | `itsi` |
| `ITSI Import Objects - *` enabled | Disabled if not using legacy modules | `itsi` |
| SIM CP base searches @ `*/5 * * * *`, per-metric | Consolidated shared base search @ `*/5` | `DA-ITSI-CP-splunk-observability` and similar |
| SAP CP base searches @ `*/5 * * * *` | `*/10` or `*/15` for less critical | `DA-ITSI-CP-sap-abap-monitoring` |
| Template services with zero entities, fully scheduled | Disabled OR converted to actual `service_template` KV objects | `SA-ITOA` |
| Auto-generated `_ACCELERATE_*` from deleted parents | Disabled | Owning app |
| Saved-search auto-summarize from deleted reports | Disabled | Owning app |

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Hitting `SA-ITOA` namespace for the housekeeping search disable | 404 from REST | Use `itsi` namespace: `/servicesNS/nobody/itsi/saved/searches/...` |
| Disabling a service that "looks" unbound but actually has entities (REST lag) | KPI tiles go from "data" to N/A in UI | Always cross-check Service Analyzer UI before disabling. If UI says bound, trust the UI |
| Disabling the kpi_base_search KV object instead of its backing saved search | The KV object has no `disabled` flag; nothing happens, search keeps running | Disable the BACKING saved search at `/servicesNS/nobody/itsi/saved/searches/Indicator - Shared - <key> - ITSI Search/disable` |
| Bulk-disabling all orphaned `kpi_base_search` objects to "reclaim performance" | Zero perf benefit (they have no scheduled backing searches), wasted effort | Per Probe 4: orphaned definitions are config bloat, not perf. Skip them |
| Disabling `Service Monitoring - Engine` because it's heavy | Service Analyzer goes blank, all health scores stop updating | Don't. It IS the engine |
| Disabling `ITSI Notable Event Search` because notable events look noisy | All ITSI alerting goes dark | Tune the policies, don't disable the engine search |
| Setting every search to cron `0 */5 * * * *` (all aligned to `:00`,`:05`...) | Saturation spikes at every 5-min boundary | Stagger crons (`*/5`, `1-59/5`, `2-59/5`, etc.) to distribute load |
| Disabling `disabled_kpis_healthscore_generator` when you actually have many disabled KPIs | Disabled KPIs stop reporting their frozen health to dashboards | Probe first: if you have <30 disabled KPIs, generator is over-served at every-minute |
| Tuning crons via `inputs.conf` edits instead of REST | Splunk Cloud doesn't allow `inputs.conf` edits in many regions | Use REST: `POST /saved/searches/<name>` with `cron_schedule=...` |
| Forgetting to verify the change actually took | Search still skips the same amount | After POST, GET the saved search and confirm `cron_schedule` reflects the new value |

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Disabling everything that appears in the top-25 skipped list without reading what it does | Some are infrastructure ITSI depends on — cascade outages | One-by-one with justification. Read the name, understand the role, check for documentation |
| Trying to fix saturation purely by adjusting `max_searches_per_cpu` higher | Splunk Cloud doesn't expose this knob; on-prem it kicks the can — under-resourced CPUs just thrash | Prune scheduled load (this skill) FIRST. Then sizing if still saturated |
| "Disable all SAP-CP searches to reclaim load" without checking which ones drive actually-bound services | KPIs on the productively-bound services go dark | Map base-search → service consumers FIRST (Probe 4 reverse). Disable only orphaned ones |
| Treating "skip rate" as the only metric of health | A search head can be quietly healthy with 5,000 skips/day if those are all genuinely redundant | The metrics that matter: (a) Service Analyzer tile freshness, (b) alert latency, (c) ad-hoc search responsiveness. Skip count is a leading indicator, not the goal itself |
| Deleting KV objects (`kpi_base_search`, `service`, `entity_type`) to "clean up" | Some have hidden references; deletion can break upstream definitions | Always disable first, observe for a week, then delete only if confirmed unused |
| Bulk-disabling all `Indicator - Shared - <hash>` saved searches | These ARE the KPI data flow for consumed base searches | Identify orphans via Probe 4, disable only those (and even then for cosmetic cleanup, not perf) |
| Optimizing for "fewest searches" instead of "fewest skipped searches" | A perfectly tuned 50-search load can be healthier than a poorly tuned 30-search load | Skips are the signal, not raw count |
| Forgetting that every CP install brings overhead | New CP installation adds ~20-100 scheduled searches that all start running immediately | Cull defaults of every CP at install time; revisit when new CP is added |

## Reference case study (2026-06-10) — the actual numbers

Starting baseline:
- **18,434 skipped searches in 24h**
- Skip rate: ~737/hour avg, peak 1,106/hour at 22:00 UTC
- Sustained almost 24/7 (no quiet hours)
- 98% of cumulative runtime in the `itsi` app

The 30-minute fix:

| Action | Daily skips reclaimed |
|---|---|
| Disabled `ITSI Import Objects - Perfmon` | 1,057 |
| Disabled `ITSI Import Objects - OS` | 931 |
| Disabled `ITSI Import Objects - TA *Nix` | 931 |
| Disabled `Splunk App for Infrastructure Alerts` | 1,183 |
| Slowed `disabled_kpis_healthscore_generator` to `*/15` | ~858 (vs 919 baseline, 93% reduction) |
| Slowed `disabled_kpis_healthscore_generator_metrics` to `*/15` | ~900 (vs 964 baseline) |
| Slowed `service_health_monitor` to `*/2` | ~480 (vs 960 baseline) |
| Slowed `service_health_metrics_monitor` to `*/2` | ~562 (vs 1,123 baseline) |
| **Total** | **~6,900 skips/day directly addressed** |

Plus indirect effects from freeing scheduler slots: previously-skipped KPI base searches stop skipping → another ~3,000 indirect.

Projected post-tuning baseline: **~8,500-9,500 skips/day** (vs 18,434), a 50%+ reduction with zero risk and zero user-visible impact.

Larger items NOT done in this round (require user judgment):
- The orphaned `_ACCELERATE_<GUID>` job in the customer-installed app (1,691 daily skips, but it's in customer's own app)
- Disabling 12 unbound SAP CP template services (~460 phantom KPIs, ~30 base searches' worth of load)
- Slowing SAP-ABAP-* base searches from 5min → 10min

These three together would likely double the savings — potentially bringing daily skips below 3,000.

## Related skills

- `splunk-itsi-api-access` — REST connectivity, tokens, capabilities (prereq)
- `splunk-itsi-content-pack-creation` — covers the Phase 5b "in-place consolidation" path which is the structural fix for per-metric base searches (often the largest perf win on heavily-CP-loaded deployments)
- `splunk-itsi-kpi-creation-via-api` — context for what KPI base searches do and how they're consumed
- `splunk-itsi-service-tree-design` — context for service hierarchies and entity binding
- `splunk-itsi-entity-binding-architecture` — entity-rule case sensitivity, the most common reason "services with zero entities" exist in the first place
