---
name: splunk-itsi-entity-health-dashboard-embed
category: itsi
description: Case studies for ITSI Entity Health xml_dashboard embed failures — unresolved host-centric embed vs validated non-host form.<token> + tr time token pattern. Covers token passthrough, form vs dashboard, EH time picker override, home app/ACL, and when to use udf_dashboard instead. Use when entity health drilldowns show blank panels, token errors, or theme issues on custom TA dashboards.
disable-model-invocation: true
---

# ITSI Entity Health — Embed Case Studies

Two outcomes on ITSI 4.21.x Cloud — one **unresolved** (host-centric), one **validated** (non-host identifier). Read **`splunk-itsi-entity-health-dashboards`** for the full agent checklist and deploy contract.

## When to use this skill

- Embed works standalone but not in Entity Health
- Choosing between host-centric OOTB pattern vs non-host validated pattern
- Non-`host` entity identifiers (`serial`, `networkId`, etc.)

---

## Case A — Non-host identifier (validated)

**Context:** TA entity type with `serial` (or similar) as identifying field · **Status:** working end-to-end in Entity Health embed

### Winning contract

1. **`<form>`** with text input `token="<field>"` (e.g. `serial`, `networkId`)
2. **`alias_param_map`:** `{"alias":"<field>","param":"form.<field>"}` — note **`form.`** prefix
3. **Hidden time input** `token="tr"` default `-24h@h` → `now`
4. Metric panels: `$tr.earliest$` / `$tr.latest$` — EH parent **overrides** panel `<earliest>` tags
5. Snapshot panels: `earliest=0`
6. Home app: **TA/CP app**, not core `itsi`
7. ACL: `owner=nobody`, global, `read=*`
8. **Do not** map `earliest`/`latest` in `alias_param_map`

### Open issue (deferred)

Splunk **dark UI preference** breaks Simple XML and Dashboard Studio embed rendering. Not a data/token bug.

---

## Case B — Host-centric custom dashboard (unresolved)

**Context:** Virtual OS / custom host entity type · **Status:** embed unresolved; white-background UI workaround used instead

### Symptoms

| Context | Result |
|---|---|
| Entity Health embed | White/unreadable or blank panels |
| Direct open / DS | OK |

### Attempts

| # | Change | Embed result |
|---|---|---|
| 1 | `<form theme="dark">`, `host_tok`, `tr_tok` | Unreadable |
| 2 | `theme="light"` | Worse (operator report) |
| 3 | `<dashboard>`, `$host$`, `$earliest$`, `$latest$` | Still broken |

### Likely gaps (not re-tested after Case A learnings)

- Never tried **`form.host`** with `<form>` + hidden `tr` time token
- Never moved home app out of `itsi`
- May need `udf_dashboard` like `ta_nix` or `DA-ITSI-OS-Host_Entity_View` custom viz

---

## Token cheat sheet

| Host-centric OOTB pattern | Non-host validated pattern |
|---|---|
| `$host$` | `$<field>$` (form input token) |
| `$earliest$` / `$latest$` on panels | `$tr.earliest$` / `$tr.latest$` (EH overrides panel times) |
| `param: "host"` | **`param: "form.<field>"`** |
| `<dashboard>` root | **`<form>`** root (for non-host TA dashboards) |

---

## Agent quick path

```
1. If identifier != host → use Case A pattern (form.<token> + tr time)
2. If identifier == host and embed still blank → check home app, ACL, tr time override, then form.host
3. If still broken → udf_dashboard (ta_nix model) or SA-ITSI-CustomModuleViz clone
4. Theme/dark UI issues → defer unless user explicitly scopes UI fix
```

## Related skills

- `splunk-itsi-entity-health-dashboards` — primary reference (checklist, REST, failure modes)
- `splunk-itsi-common-errors` — `wineventlog-ds`, `LOOKUP-dropdowns` ambient errors
