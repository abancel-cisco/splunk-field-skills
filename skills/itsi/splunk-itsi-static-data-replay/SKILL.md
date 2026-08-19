---
name: splunk-itsi-static-data-replay
category: itsi
description: Make static / historical / one-shot-loaded data appear "live" to Splunk ITSI KPIs using the earliest=1 + `eval _time=now()` macro trick. Covers why ITSI KPI base searches see nothing when event _time is in the past (or when a source is a periodic full-table dump that never advances), the single-macro pattern that centralizes the override so one edit flips back to live, the mandatory dedup for re-emitted snapshot rows, how inline earliest/latest beats ITSI's dispatch window, and validation via the indicator dispatch + itsi_summary. Use when ITSI KPIs read 0 / N-A / gray on data that clearly exists in the index, when demoing on frozen or replayed datasets (ERP document extracts, PowerConnect exports, old project data), when the user mentions static data, historical timestamps, backfill, replay, "trick ITSI into thinking it's live", earliest=1, _time=now, or a macro to override timestamps for KPIs.
disable-model-invocation: true
---

# ITSI Static-Data Replay (earliest=1 + _time=now)

A deliberate, dirty workaround: force static/historical data to be evaluated by ITSI KPIs as if it were arriving live. Use only when you cannot get a real live feed (demos, one-shot loads, frozen datasets). Isolate the hack in ONE macro so production cut-over is a single edit.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When you need it

ITSI KPI base searches run on a rolling window (e.g. dispatch `earliest=-330s latest=-30s`) against **`_time`**. They return nothing when:

- Event `_time` is in the past (historical load, `_time` = a business timestamp like invoice creation date).
- The source is a **periodic full-table dump / snapshot** (PowerConnect table extracts, config exports): the same rows are re-emitted every cycle, nothing new ever enters the rolling window.
- You are replaying a frozen dataset months later.

Symptom: data is obviously in the index (`| stats count` over all time is non-zero) but KPIs show `0` / `N/A` / gray health.

## The trick

Two moves, both centralized in one macro:

1. **`earliest=1 latest=now`** as *inline* time terms in the base search. Inline time modifiers override ITSI's dispatch window, so historical rows are always retrieved regardless of the KPI's configured window.
2. **`| eval _time=now()`** at the end, so every output row is stamped "now" and ITSI plots/evaluates it at the current time (live-looking, stable trend on static data).

If the source re-emits rows (snapshot dumps), **dedup first** to the real grain, else counts/sums are inflated by the number of collection cycles.

## Pattern: one macro = one cut-over point

Put the whole retrieval + normalize + dedup + replay in a single Splunk macro. The ITSI base search calls the macro, then does its `stats`. To go live, edit ONLY this macro (delete the two replay lines).

```spl
# macro: cockpit_ap_invoices_src   (app: itsi, shared global so the indicator search resolves it)
index=erp sourcetype=erp:doc source=PR1 "/DOCFLOW/HEADER" DOC_NO=* earliest=1 latest=now   <-- replay line 1
| dedup DOC_GUID sortby -_indextime          <-- snapshot dump: collapse to 1 row per entity
| eval posted=if(DOC_NO!="" AND DOC_NO!="0000000000","posted","not_posted")
| eval fi_flag=if(FI_MM_FLG=="FI",1,0), mm_flag=if(FI_MM_FLG=="MM",1,0)
| eval _time=now()                                <-- replay line 2
```

ITSI base search (`base_search` field) then follows the normal shared-base pattern:

```spl
`cockpit_ap_invoices_src`
| stats dc(DOC_GUID) as total_invoices sum(fi_flag) as fi_invoices ...
| eval ITSIUniqueId="GLOBAL"
```

### Going live later

Edit the macro only:
- remove `earliest=1 latest=now` (let ITSI's window apply)
- remove `| eval _time=now()`
- keep/remove `dedup` depending on whether the live feed still snapshots.

Every KPI and base search that references the macro flips automatically. No KPI edits.

## Create the macro via REST

```bash
# create (app=itsi so the auto-generated "Indicator - Shared - <BS> - ITSI Search" resolves it)
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "name=<macro_name>" --data-urlencode "definition=<SPL>" \
  "$URL/servicesNS/nobody/itsi/configs/conf-macros"
# share global
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "sharing=global" --data-urlencode "owner=nobody" --data-urlencode "perms.read=*" \
  "$URL/servicesNS/nobody/itsi/configs/conf-macros/<macro_name>/acl"
```

Args-in-macro caveat: a `(n)` macro (with arguments) needs the arg count in the name, e.g. `mymacro(1)`, and `$arg$` tokens in the definition. For the replay trick a 0-arg macro is simplest.

## Validate

```bash
# force the indicator to compute AND write severity to itsi_summary
curl -sk -X POST -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "trigger_actions=1" \
  "$URL/servicesNS/nobody/itsi/saved/searches/Indicator%20-%20Shared%20-%20<BS_KEY>%20-%20ITSI%20Search/dispatch"
```

```spl
index=itsi_summary itsi_service_id=<svc_key> earliest=-30m latest=now
| stats latest(alert_value) as v latest(alert_level) as lvl latest(alert_severity) as sev by kpi
```

Expect real `alert_value`, `alert_level=2`, `sev=normal` (not `-1`/`unknown`). `_time=now()` means the summary events land at current time, so a short `earliest=-30m` window finds them.

## Gotchas

| Gotcha | Fix |
|---|---|
| KPIs still empty after macro | Macro not shared / wrong app — the indicator runs in app `itsi`; share the macro global |
| Counts N× too high | Snapshot dump re-emits rows; add `dedup <key> sortby -_indextime` |
| Flat trend line | Expected: static data stamped at now() is a flat series. Fine for functional demos; do not sell it as a real trend |
| `_time=now()` but still nothing | Something else filters `_time` (a `where`/`bucket earliest`); ensure earliest=1 is the effective floor |
| Left the hack in for prod | This is the whole reason it lives in one macro — track it and remove at cut-over |

## Honesty

This is a demo workaround, not a data-quality fix. Say so to whoever reads the dashboard: KPI values are real, the *timing* is synthetic. The real fix is a live feed (or event-time-correct backfill). Keep the macro name self-documenting (e.g. `*_src`, comment the replay lines) so nobody ships it to production by accident.

## Related skills

- `splunk-itsi-kpi-creation-via-api` — the base search / KPI objects this macro feeds
- `splunk-itsi-api-access` — REST connectivity for macro + indicator dispatch
