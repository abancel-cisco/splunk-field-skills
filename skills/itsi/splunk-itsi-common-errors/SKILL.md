---
name: splunk-itsi-common-errors
category: itsi
description: Documents fixes for five recurring ITSI errors — (1) missing eventtype wineventlog-ds (install Splunk Add-on for Windows, then disable unneeded TA searches on the ITSI search head), (2) Could not load lookup=LOOKUP-dropdowns (run dropdowns_lookup_migrate without append=t, set dropdowns.csv permissions to global), (3) recommendthresholdtemplate external command failure (downgrade Splunk AI Toolkit to 5.6.* and Splunk SA Scientific Python to 4.2.* on ITSI 4.21; on Splunk Cloud open a support ticket), (4) Notable Event Actions queue backlog / NEAP outage from earemotesearch ProxyError (set NO_PROXY for the SH's own hostname in splunk-launch.conf, clear itsi_notable_event_actions_queue), (5) KPI historical/trend widget shows "The selected KPI has no data in the summary index. Backfill the KPI." even though index=itsi_summary clearly has recent events — because the historical/sparkline widgets read the itsi_summary_metrics METRICS index (via mstats), and the KPI's "Indicator - Shared - <BS> - ITSI Search" skipped recent cycles under search-concurrency saturation ("maximum number of concurrent historical scheduled searches has been reached"), leaving gaps in BOTH indexes; fix by spreading indicator schedules (alert_period) and cutting concurrent load, NOT by clicking Backfill; for split-by pseudo-entity KPIs an individual pseudo-entity's per-entity history is legitimately sparse. Validated on ITSI 4.21.* and ITSI 5.0.* (sections 1–2, 5). Use when ITSI UI or searches fail with these exact messages, during fresh ITSI installs, content-pack imports, KPI threshold AI setup, Unix dashboard pack troubleshooting, when webhook/notable-event actions stop firing behind an outbound proxy, or when KPI trend/sparkline charts read empty while the summary index has data.
disable-model-invocation: true
---

# ITSI — Common Errors (and Fixes)

Catalog of production errors seen on ITSI **4.21.X** and **5.0.X** stacks. Each section: symptom → root cause → fix → verify.

**Versions validated:**

| Section | ITSI 4.21.* | ITSI 5.0.* | Notes |
|---|---|---|---|
| §1 `wineventlog-ds` | Yes | **Yes** (lab instance, 2026-07-03) | Same root cause and fix |
| §2 `LOOKUP-dropdowns` | Yes | **Yes** (lab instance, 2026-07-03) | Same root cause and fix |
| §3 `recommendthresholdtemplate` | Yes | Not re-validated | Likely 4.21-specific; upgrade to 5.0 may resolve |
| §4 `earemotesearch` ProxyError / NEAP backlog | Yes | Not re-validated | Proxy-egress dependent; applies wherever the SH sits behind an outbound proxy |
| §5 KPI "no data in the summary index / Backfill" | Likely | **Yes** (ITSI Cloud 5.x, 2026-07-29) | Concurrency-ceiling dependent; any single-SH / capacity-limited stack |

Re-check SplunkBase compatibility matrices after major upgrades.

## When to use this skill

- Search or UI error: `Eventtype 'wineventlog-ds' does not exist or is disabled.`
- Search or UI error: `Could not load lookup=LOOKUP-dropdowns` (or `lookup table 'dropdownsLookup' does not exist`)
- KPI Threshold AI error: `Error in 'recommendthresholdtemplate' command: External search command exited unexpectedly with non-zero error code 1.`
- Fresh ITSI install where Windows eventtype macros fail
- Unix dashboards content pack (`DA-ITSI-CP-unix-dashboards`) installed but dropdown lookups break
- User tries ITSI 4.21 AI threshold recommendations and gets external-command failure
- Notable/webhook actions stop firing and `_internal` shows `Error in 'earemotesearch' command: ProxyError ... port=8089 ... 403 Forbidden`, or `itsi_notable_event_actions_queue` grows abnormally large
- KPI trend / sparkline / threshold-preview shows `The selected KPI has no data in the summary index. Backfill the KPI.` even though `index=itsi_summary` has recent events for that KPI

## Quick triage

| Error substring | Section | Human action required? |
|---|---|---|
| `wineventlog-ds` | [§1](#1--eventtype-wineventlog-ds-does-not-exist-or-is-disabled) | Yes — install Windows TA |
| `LOOKUP-dropdowns` / `dropdownsLookup` | [§2](#2--could-not-load-lookuplookup-dropdowns) | Usually no — run migrate search + fix perms |
| `recommendthresholdtemplate` | [§3](#3--recommendthresholdtemplate-external-command-error) | Yes on Cloud — support ticket for downgrade |
| `earemotesearch` `ProxyError` / queue backlog | [§4](#4--itsi-notable-event-actions-queue-backlog--neap-outage-due-to-earemotesearch-proxy-errors) | Yes — proxy/`no_proxy` change (Cloud: support ticket) |
| `no data in the summary index` / `Backfill the KPI` | [§5](#5--the-selected-kpi-has-no-data-in-the-summary-index-backfill-the-kpi) | Usually no — spread indicator schedules / cut concurrent load; do **not** click Backfill |

---

## 1 — `Eventtype 'wineventlog-ds' does not exist or is disabled.`

### Symptom

Searches, KPIs, dashboards, or macros reference the `wineventlog-ds` eventtype. Splunk returns:

```
Eventtype 'wineventlog-ds' does not exist or is disabled.
```

Often surfaces when Windows-related ITSI content is present but the Windows TA is not installed on the search head.

### Root cause

`wineventlog-ds` is defined by the **Splunk Add-on for Microsoft Windows** (`Splunk_TA_windows`). Without that app, the eventtype does not exist.

On ITSI 5.0 stacks with Windows content packs (`DA-ITSI-CP-windows`, `DA-ITSI-CP-windows-dashboards`) but **no** `Splunk_TA_windows`, this error still appears — confirmed on a lab instance (Splunk 10.4.1 + ITSI 5.0, 2026-07-03).

### Fix

**Step 1 — Prompt the human to install the add-on**

The agent cannot install Splunkbase apps on the stack. Ask a Splunk admin to install:

- **Splunk Add-on for Microsoft Windows**
- Splunkbase: https://splunkbase.splunk.com/app/742
- Match the add-on version to the Splunk / Splunk Cloud stack per SplunkBase compatibility notes.
- On a lab instance: `Splunk_TA_windows` **10.0.0** on Splunk **10.4.1** worked.

On **Splunk Cloud**, installation is via **Admin Config Service (ACS)** or the stack admin portal — not by dropping files into `etc/apps/`.

**Step 2 — Minimize load on the ITSI search head**

The ITSI search head usually does **not** need to collect Windows data. After install, ensure the TA does not add unnecessary scheduled searches or inputs:

1. **Settings → Searches, reports, and alerts** — filter by app `Splunk_TA_windows` (or the installed Windows TA app name). **Disable** every saved search that is not explicitly required for ITSI/KPI functionality on this SH.
2. **Settings → Data inputs** — if any Windows inputs were enabled on the ITSI SH, **disable** them unless this SH is intentionally a Windows data collection point.
3. **Settings → Event types** — confirm `wineventlog-ds` exists and is **enabled** (the eventtype itself must exist; only collection/scheduling should stay off).

Goal: satisfy the eventtype dependency without turning the ITSI SH into a Windows forwarder or running TA maintenance searches at scale.

### Verify

```spl
| rest /servicesNS/-/-/admin/eventtypes splunk_server=local
| search title="wineventlog-ds"
| table title disabled
```

Expect one row, `disabled=0`.

Re-run the search or open the ITSI view that previously failed — the eventtype error should be gone.

### Pitfalls

| Pitfall | Why it hurts | What to do |
|---|---|---|
| Installing the TA and leaving all default scheduled searches enabled | Extra CPU / search concurrency on the ITSI SH | Disable all non-essential TA searches after install |
| Installing the **full** Splunk for Windows app instead of the **add-on** | Heavier footprint; may enable inputs you do not want | Install app **742** (Add-on), not the UF/full product unless required |
| Fixing on indexer but not search head | Eventtypes resolve on the SH where the search runs | Install/enable on the **ITSI search head** |
| Assuming ITSI 5.0 no longer needs the Windows TA | Windows CPs ship dashboards/macros, not the TA eventtypes | Still install `Splunk_TA_windows` on the SH |

---

## 2 — `Could not load lookup=LOOKUP-dropdowns`

### Symptom

```
Could not load lookup=LOOKUP-dropdowns
```

Or the related LookupOperator message:

```
The lookup table 'dropdownsLookup' does not exist. It is referenced by configuration ...
```

Typically after installing the ITSI Unix dashboards content pack (`DA-ITSI-CP-unix-dashboards`) or when automatic lookup `dropdownsLookup` fires before the CSV exists.

### Root cause

The content pack defines:

- CSV lookup **`dropdowns.csv`**
- Automatic lookup **`dropdownsLookup`** (references `LOOKUP-dropdowns`)

The CSV is **not shipped** in the package. It is created/updated by the scheduled saved search **`dropdowns_lookup_migrate`**. If that search never succeeded (field-name issues, permissions, empty entity set), the CSV file is missing and every automatic lookup fails.

On ITSI 5.0 (lab instance): `dropdowns_lookup_migrate` exists in `DA-ITSI-CP-unix-dashboards` but is **disabled** by default — the CSV is never auto-created on fresh install.

See Splunk Community: [Why am I getting error "lookup table 'dropdownsLookup' does not exist"?](https://community.splunk.com/t5/Splunk-Search/Why-am-I-getting-error-quot-lookup-table-dropdownsLookup-does/m-p/657927)

### Fix

**Step 1 — Run the migrate search once, without `append=t`**

In Splunk Search (or via REST dispatch), run the saved search **`dropdowns_lookup_migrate`** as a **new** search — **not** appended to another pipeline.

Critical detail from the field fix: run it **without** `append=t`. The scheduled version may use `append=t` for incremental updates; the **first** creation must run standalone to seed `dropdowns.csv` with correct field names.

If there are no entities yet, the lookup may contain only a single row such as `all_hosts` — that is expected.

**Step 2 — Set `dropdowns.csv` permissions to Global**

**Settings → Lookups → Lookup table files** → find **`dropdowns.csv`** → **Permissions → All apps (global)**.

Without global sharing, other apps referencing the automatic lookup cannot resolve the CSV.

**Step 3 — Wait for bundle replication**

On clustered search heads or indexer clusters, allow a few minutes for `dropdowns.csv` to replicate before retesting.

### Verify

```spl
| inputlookup dropdowns.csv
| head 5
```

Should return rows (at minimum `all_hosts` when no entities exist).

Re-open the Unix dashboard or KPI that triggered the error.

### REST dispatch (optional)

```bash
TOKEN=$ITSI_TOKEN
URL=$ITSI_URL

curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  "$URL/servicesNS/nobody/DA-ITSI-CP-unix-dashboards/saved/searches/dropdowns_lookup_migrate/dispatch"
```

Adjust owner/app if the search lives under a different namespace on the stack.

**If dispatch returns 400 because the saved search is disabled** (common on fresh installs and ITSI 5.0): seed the CSV with a one-shot ad hoc search instead of enabling the scheduled search:

```spl
| makeresults count=1
| eval host="*", unix_category="all_hosts", unix_group="default"
| table host unix_category unix_group
| outputlookup dropdowns.csv
```

Run in app context `DA-ITSI-CP-unix-dashboards` (REST: `POST /servicesNS/nobody/DA-ITSI-CP-unix-dashboards/search/jobs`). Do **not** use `append=t` on first run.

Then verify:

```spl
| inputlookup dropdowns.csv
| makeresults | eval host="testhost" | lookup dropdownsLookup host OUTPUT unix_category unix_group
```

Expect `unix_category=all_hosts`. On Splunk Cloud the CSV may not appear immediately in **Settings → Lookups** REST (`lookup-table-files` 404) even when `| inputlookup` works — trust the SPL verification. If `dropdowns_lookup_migrate` is **disabled** in `DA-ITSI-CP-unix-dashboards`, `DA-ITSI-CP-windows-dashboards`, or `itsi`, prefer the seed SPL above over enabling the scheduled search for first-time creation. Set global ACL via UI if the file appears in Lookups; REST ACL POST may 404 until the object is registered.

### Lab fix recipe (ITSI 5.0, 2026-07-03)

```bash
# Seed via REST oneshot
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode 'search=| makeresults count=1 | eval host="*", unix_category="all_hosts", unix_group="default" | table host unix_category unix_group | outputlookup dropdowns.csv' \
  "$URL/servicesNS/nobody/DA-ITSI-CP-unix-dashboards/search/jobs"

# Set global sharing
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  -d "sharing=global" -d "owner=nobody" \
  "$URL/servicesNS/nobody/DA-ITSI-CP-unix-dashboards/data/lookup-table-files/dropdowns.csv/acl"
```

### Pitfalls

| Pitfall | Why it hurts | What to do |
|---|---|---|
| Only fixing automatic lookup sharing, not creating the CSV | Lookup definition exists but file is still missing | Run `dropdowns_lookup_migrate` first |
| Running migrate **with** `append=t` on first run | Base file never created with correct schema | First run: no `append=t` |
| Testing before SHC bundle replication | False negative on peer nodes | Wait 2–5 minutes, retry |
| Enabling `dropdowns_lookup_migrate` on empty entity set | May still fail; disabled by default on 5.0 | Use seed SPL for first creation |

---

## 3 — `recommendthresholdtemplate` external command error

### Symptom

In **ITSI → Configure → Services → [service] → KPI → Thresholds**, using **AI threshold recommendations** fails with:

```
Error in 'recommendthresholdtemplate' command: External search command exited unexpectedly with non-zero error code 1.
```

### Root cause

ITSI 4.21.* AI threshold recommendations depend on:

- **Splunk AI Toolkit** / **Splunk_ML_Toolkit** (MLTK)
- **Splunk SA Scientific Python** (PSC) — platform-specific builds (Linux, macOS, Windows)

ITSI 4.21.* is compatible with specific **older** major versions. Newer MLTK / PSC releases on the stack cause the `recommendthresholdtemplate` custom command to exit with code 1.

Official Splunk article: [AI Threshold Recommendation Fails with External Search Command Error - ITSI 4.21.*](https://splunk.my.site.com/customer/s/article/AI-Threshold-Recommendation-Fails-with-External-Search-Command-Error---ITSI-4-21) (article 000021119)

**Supported versions for ITSI 4.21.* (as of 2026-04-27):**

| App | Target version | Avoid |
|---|---|---|
| Splunk AI Toolkit / `Splunk_ML_Toolkit` | **5.6.*** | 5.7.* and newer |
| Splunk SA Scientific Python (per OS) | **4.2.*** | Newer major versions |

**ITSI 5.0:** This error was not re-tested on a lab instance. Splunk's long-term guidance is to upgrade to ITSI 5.* — threshold AI may work with current MLTK/PSC on 5.0. If the error appears on 5.0, check Splunk docs for updated compatibility before downgrading.

### Fix — Splunk Cloud

The agent **cannot** downgrade apps on Splunk Cloud. **Prompt the human** to:

1. Open a **Splunk Support** case (Splunk Cloud change request).
2. Request downgrade of:
   - `Splunk_ML_Toolkit` → latest **5.6.*** patch
   - `Splunk_SA_Scientific_Python_*` (Linux / macOS / Windows as applicable) → latest **4.2.*** patch
3. Provide a **maintenance window**.
4. Note: if the stack runs **both Enterprise Security (ES) and ITSI**, MLTK/PSC versions may be **locked across all search heads** — downgrade may be **not authorized**. Support will confirm.

### Fix — On-premises ITSI search head

1. **Settings → Apps → Manage Apps** — note current MLTK and PSC versions.
2. From [Splunkbase](https://splunkbase.splunk.com/) → each app → **Version History** → download the latest **5.6.*** (MLTK) and **4.2.*** (PSC) installers compatible with your Splunk version.
3. **Uninstall** the too-new apps from the ITSI search head.
4. **Install** the older versions into `etc/apps/` (or via `splunk install app`).
5. **Restart** the search head.
6. Re-test AI threshold recommendations on a KPI.

Splunk UI does not support downgrade in place — uninstall + install older build is required.

### Verify

1. Confirm app versions:

```spl
| rest /servicesNS/-/-/apps/local splunk_server=local
| search title="Splunk_ML_Toolkit" OR title="Splunk_SA_Scientific_Python*"
| table title version
```

2. Open a KPI → **Thresholds** → run **AI recommendation** — should complete without the external-command error.

### Pitfalls

| Pitfall | Why it hurts | What to do |
|---|---|---|
| Upgrading MLTK to "latest" on an ITSI 4.21 stack | Breaks `recommendthresholdtemplate` | Pin MLTK 5.6.* until ITSI 5.* |
| Installing PSC for wrong OS flavor | Command still fails | Install the PSC build matching the SH OS |
| ES + ITSI on Cloud — attempting self-downgrade | Change rejected or breaks ES SH parity | Support ticket; accept "not possible" if denied |
| Assuming all ML features break | Only the ITSI threshold AI path uses this command | Other ITSI KPI features may work fine |
| Downgrading MLTK on ITSI 5.0 without checking | May be unnecessary on 5.0 | Test threshold AI first; check 5.0 release notes |

---

## 4 — ITSI Notable Event Actions Queue Backlog & NEAP Outage due to `earemotesearch` Proxy Errors

### Symptom

Notable Event Aggregation Policies (NEAPs) stop processing action rules (e.g., webhook notifications do not reach their destinations).
The KV store collection `itsi_notable_event_actions_queue` grows abnormally large, resulting in system degradation, search timeouts, and general search head instability.
The `_internal` logs show high frequencies of the following error:
```
Error in 'earemotesearch' command: ProxyError at "/opt/splunk/etc/apps/SA-ITOA/lib/SA_ITOA_app_common/requests/adapters.py", line 513 : HTTPSConnectionPool(host='itsi.example.com', port=8089): Max retries exceeded with url: /services/server/info (Caused by ProxyError('Cannot connect to proxy.', OSError('tunnel connection failed: 403 Forbidden')))
```

### Root cause

1. **Ad-hoc Search Dispatch:** When an episode triggers a webhook action rule, the ITSI Rules Engine dispatches an ad-hoc search command that uses `earemotesearch` to query the macro `itsi_notable_group_lookup` on the search head.
2. **Local Request Routing:** The `earemotesearch` custom command connects via Python's `requests` library to the search head's management port (`8089`) using its external hostname (e.g., `https://itsi.example.com:8089`).
3. **Outbound Proxy Egress Rule Violation:** If the Search Head environment has an outbound proxy configured, Python routes this local REST API request through the proxy. However, typical outbound proxy configurations restrict `CONNECT` requests to port `443` and block port `8089` (`403 Forbidden` or connection timeout).
4. **Queue Consumer Starvation:** The search threads hang or fail, exhausting the worker threads of the `itsi_notable_event_actions_queue_consumer` service (alpha, beta, gamma). While workers are starved, incoming notable event actions continue to pile up in the `itsi_notable_event_actions_queue` KV store.

### Fix

**Step 1 — Emergency queue cleanup (if stack is unresponsive)**
If the queue is too large, clear the backlog by running a search to write an empty set to the KV store (or delete entries via the REST API):
```spl
| makeresults | fields - _time | outputlookup itsi_notable_event_actions_queue
```

**Step 2 — Configure `no_proxy` environment variable**
Configure the Search Head's local environment to bypass the proxy for local loopback and external endpoints. 
Add the search head's external host names (e.g. `itsi.example.com` and `localhost`) to the `no_proxy` / `NO_PROXY` environment variable in `splunk-launch.conf`:
```ini
# Add to $SPLUNK_HOME/etc/splunk-launch.conf
NO_PROXY = localhost,127.0.0.1,itsi.example.com
no_proxy = localhost,127.0.0.1,itsi.example.com
```
*Note: On Splunk Cloud, this configuration change must be requested via a support ticket.*

**Step 3 — Egress rule adjustment**
Alternatively, update the outbound corporate proxy settings to allow the Search Head to connect to its own external endpoint on port `8089`.

### Verify

1. Run the following search to verify `ProxyError` logs have ceased:
```spl
index=_internal "earemotesearch" "ProxyError" earliest=-1h
```
2. Verify the notable event actions queue size is maintained at or close to `0`:
```spl
| inputlookup itsi_notable_event_actions_queue | stats count
```

### Pitfalls

| Pitfall | Why it hurts | What to do |
|---|---|---|
| Modifying core ITSI macros to append heavy lookups/joins | Exacerbates search execution times and increases queue worker starvation sensitivity | Use Correlation Search pre-enrichment instead of dynamic lookups |
| Clearing the queue without resolving the proxy blockage | The backlog will immediately begin accumulating again | Perform proxy routing bypass first, then clear the queue |

---

## 5 — `The selected KPI has no data in the summary index. Backfill the KPI.`

### Symptom

A KPI's **historical / trend / sparkline** view shows:

```
The selected KPI has no data in the summary index. Backfill the KPI.
```

Appears in the KPI **thresholds preview**, the **Service Analyzer** KPI trend flip, and **Deep Dive** lanes. Reported for **both** the aggregate KPI **and** its per-entity (split-by) breakdown. Yet a raw search proves data exists:

```spl
index=itsi_summary itsi_service_id=<SVC> itsi_kpi_id=<KPI> earliest=-2h latest=now | stats count
```
returns a healthy, recent count. So the message looks like a lie — and this is what makes it confusing.

### Root cause

**The KPI historical / sparkline widgets do NOT read the `itsi_summary` events index. They read the `itsi_summary_metrics` METRICS index via `mstats`.** The real UI search (from `_audit`) looks like:

```spl
| mstats latest(alert_value) AS alert_value
    WHERE `get_itsi_summary_metrics_index` AND itsi_service_id=<SVC>
    `kpi_level_metrics_source_filter` fillnull_value="N/A"
    `metrics_service_level_kpi_only`      <-- aggregate:  ((is_service_max_severity_event=0 is_service_aggregate=1) OR scoretype="service_health")
    earliest=<e> latest=<l> by itsi_kpi_id span=60s
| `interpolate_kpi_data(<e>,<l>)` | stats sparkline(avg(alert_value),60s) AS spark BY itsi_kpi_id
```
Entity level uses `metrics_entity_level_kpi_only` = `is_service_aggregate=0`. Macros: `get_itsi_summary_metrics_index` = `index="itsi_summary_metrics"`.

Both the **events** row (sourcetype `stash` → `itsi_summary`) and the **metric** points (sourcetype `itsi_summary:metrics` → `itsi_summary_metrics`) are written by the **same** `Indicator - Shared - <BS> - ITSI Search` in one execution. Therefore:

> If that indicator search **SKIPS** a scheduled run, **both** indexes miss that cycle for **every** KPI on that base search (aggregate *and* all pseudo-entities). When enough recent cycles are skipped that the visible window has zero metric points, the widget reports "no data … Backfill." It **self-heals** on the next successful cycle, so it flickers in and out — easy to mistake for a data-pipeline bug.

On a single-search-head ITSI Cloud stack the skip reason (in `index=_internal sourcetype=scheduler status=skipped`) is:

```
The maximum number of concurrent historical scheduled searches on this instance has been reached
```
(and the per-search variant `... maximum number of concurrent running jobs for this historical scheduled search ...`). Triggers: many 5-minute indicator searches colliding on the same cron minute, over-scheduled/expensive base searches, content-pack indicator sprawl, and **heavy ad-hoc searches run in the same window** (e.g. multi-day `dc()` over a raw index during a demo). `service_health_metrics_monitor` (writes the health-score metric) skips for the same reason → service-health sparkline gaps too.

Note: "Backfill the KPI" writes historical **events** into `itsi_summary` by re-running the base search over the past — it does **not** repopulate the metrics index the widget reads, and it does nothing about the ongoing skip. So clicking Backfill is the wrong fix here.

### Diagnosis

1. Prove the events index has data but the widget is empty (see Symptom SPL). Then check the **metrics** index directly:
```spl
| mstats latest(alert_value) AS v WHERE `get_itsi_summary_metrics_index`
    itsi_service_id=<SVC> earliest=-2h latest=now by itsi_kpi_id span=15m
| stats count AS pts values(v) AS vals by itsi_kpi_id
```
Gaps / missing buckets here = the real cause.

2. Confirm indicator skips (and the reason) in the affected window:
```spl
index=_internal sourcetype=scheduler status=skipped earliest=-3h latest=now
    (savedsearch_name="Indicator - Shared - *" OR savedsearch_name="service_health_metrics_monitor")
| stats count by savedsearch_name reason
```
Expect `reason="The maximum number of concurrent historical scheduled searches ..."`.

### Fix (durable — reduce skips)

- **Spread indicator schedules.** Change the **base search** `alert_period` (e.g. 5 → 15/30 min) on the `kpi_base_search` object via the ITSI API. ITSI regenerates the `Indicator - Shared - …` saved search with a recalculated/staggered cron minute. Do **not** hand-edit the generated saved search's cron — it gets overwritten. (See `splunk-itsi-performance-tuning`.)
- **Cut concurrent load.** Disable unused content-pack indicator searches; retire chronically-skipping / over-expensive base searches; stagger cron minutes so 5-min searches don't all fire on `:00/:05/:10`.
- **Don't run heavy ad-hoc searches during demos** on a single-SH stack — they eat the same concurrency pool the indicators need.
- Do **not** rely on clicking **Backfill** — it repopulates events, not the metrics the widget reads.

### Verify

```spl
index=_internal sourcetype=scheduler status=skipped earliest=-1h
    savedsearch_name="Indicator - Shared - *" | stats count
```
Skip count should drop toward 0. Re-open the KPI trend — the sparkline renders. Confirm metric continuity with the mstats query above (no missing buckets).

### Pseudo-entity nuance (expected, not a skip)

For **split-by pseudo-entity** KPIs (e.g. split by `INVOICE_GUID`), an *individual* pseudo-entity is short-lived (invoices appear and clear). When you drill a **specific** stale pseudo-entity, its per-entity history is legitimately empty over a normal window → the same "no data / Backfill" message even when the pipeline is perfectly healthy. This is inherent to pseudo-entities, not a concurrency skip. The **aggregate** and the **live** pseudo-entities still render.

### Pitfalls

| Pitfall | Why it hurts | What to do |
|---|---|---|
| Assuming the trend reads `itsi_summary` events | You "prove" data exists there and conclude ITSI is broken | The widget reads `itsi_summary_metrics` (metrics) via `mstats` — check *that* index |
| Clicking **Backfill the KPI** | Writes historical events, not metrics; ignores the skip; wastes concurrency (more skips) | Fix scheduling/concurrency instead |
| Hand-editing the generated `Indicator - Shared - …` cron | ITSI regenerates it from the base search and overwrites your change | Set `alert_period` on the `kpi_base_search` object |
| Reading a spike of concurrency skips as a KPI-config bug | Leads to needless KPI rebuilds | It's environment capacity; spread schedules / cut load |
| High-cardinality pseudo-entity per-entity drill shows empty | Mistaken for outage | Expected for short-lived entities; use aggregate + live entities |

---

## Agent workflow checklist

When the user pastes one of these errors:

```
- [ ] Match error text to section 1, 2, 3, or 4
- [ ] State ITSI version (4.21.* or 5.0.*)
- [ ] For §1: instruct human to install Windows TA 742; then disable unneeded TA searches/inputs on ITSI SH
- [ ] For §2: run dropdowns_lookup_migrate (no append=t) OR seed SPL; set dropdowns.csv global; verify | inputlookup
- [ ] For §3: check MLTK + PSC versions; Cloud → support ticket; on-prem 4.21 → downgrade to 5.6.* / 4.2.*
- [ ] For §4: set NO_PROXY for the SH's own hostname(s) in splunk-launch.conf (Cloud → support ticket); clear itsi_notable_event_actions_queue if degraded; then confirm ProxyError logs cease
- [ ] For §5: confirm events index has data; check itsi_summary_metrics via mstats; check scheduler skips + reason; spread indicator alert_period / cut concurrent load; do NOT click Backfill; note pseudo-entity per-entity history is expectedly sparse
- [ ] Run verification SPL from the matching section
- [ ] Document what was changed and what still needs human action
```

## Related skills

- `splunk-itsi-api-access` — REST tokens and endpoints for dispatching saved searches
- `splunk-itsi-kpi-creation-via-api` — KPI threshold configuration outside the AI recommender
- `splunk-itsi-performance-tuning` — if Windows TA install adds unexpected search load, tune concurrency
- `splunk-itsi-50-upgrade` — post-upgrade validation; cross-ref for threshold AI on 5.0

## References

| Topic | Link |
|---|---|
| Splunk Add-on for Microsoft Windows | https://splunkbase.splunk.com/app/742 |
| dropdownsLookup community thread | https://community.splunk.com/t5/Splunk-Search/Why-am-I-getting-error-quot-lookup-table-dropdownsLookup-does/m-p/657927 |
| ITSI 4.21 AI threshold / recommendthresholdtemplate | https://splunk.my.site.com/customer/s/article/AI-Threshold-Recommendation-Fails-with-External-Search-Command-Error---ITSI-4-21 |
