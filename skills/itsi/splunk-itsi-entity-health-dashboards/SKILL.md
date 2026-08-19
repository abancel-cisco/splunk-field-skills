---
name: splunk-itsi-entity-health-dashboards
category: itsi
description: Documents how ITSI Entity Health embeds custom Simple XML dashboards (xml_dashboard drilldowns on entity_type.dashboard_drilldowns), the token/time/ACL/app contract validated on ITSI 4.21.x Cloud, and why dashboards often fail only inside the embed. Covers form vs dashboard XML, form.<token> alias_param_map for non-host identifiers, hidden tr time token when EH overrides panel earliest/latest, home app in TA/CP not itsi, global ACL owner=nobody, reference patterns DA-ITSI-OS-Host_Entity_View and host_information, and known dark-UI theme issues. Use when custom entity dashboards break only in Entity Management or Entity Health, when wiring dashboard_drilldowns on custom entity types, or when building TA/CP entity views.
disable-model-invocation: true
---

# ITSI Entity Health — Custom Dashboard Embed

How ITSI **Entity Health** loads custom dashboards, why they often **fail only in the embed**, and the **validated contract** for non-host entity identifiers on ITSI 4.21.x / Splunk Cloud.

**Validated on:** ITSI 4.21.x, Splunk Cloud (multiple stacks).

## When to use this skill

- Custom dashboard works standalone but is **broken in Entity Health** (blank panels, no data, token errors)
- Wiring `dashboard_drilldowns` on custom entity types (TA or content pack)
- Choosing home app, ACL, `<form>` vs `<dashboard>`, and token names
- Entity identifier is **not** `host` (e.g. `serial`, `networkId`, `deviceId`)

## Two viewing contexts (do not conflate)

| Context | Entry | What supplies entity id & time |
|---|---|---|
| **Standalone** | `/app/<home_app>/<dashboard_id>` | Form inputs, `<init>` defaults, URL params |
| **Entity Health embed** | Entity Management → entity → Entity Health tab | **ITSI parent frame** passes tokens into iframe |

**Always test Entity Health**, not only the standalone app view.

---

## Validated pattern — non-host identifier + `<form>` (ITSI 4.21.x)

Use when the entity type identifies devices by a field other than `host` and data may be sparse relative to the EH time picker default.

### What worked

| Setting | Value | Why |
|---|---|---|
| Root element | **`<form version="1.1">`** | Works with text inputs + ITSI token injection |
| Home app | **TA or CP app** (e.g. `Splunk_TA_<vendor>`) | **Not** core `itsi` — OOTB xml dashboards ship in CP/TA apps; `itsi` home + `isVisible=False` makes dashboards undiscoverable |
| ACL | `owner=nobody`, `sharing=global`, `perms.read=*` | Private dashboards → "deleted / not a Splunk dashboard" in embed |
| `isVisible` | `True` (discoverable) or `False` (embed-only) | Match operator need |
| Entity token input | `<input type="text" token="<field>">` with `<default>` | Binds entity field from drilldown |
| `alias_param_map` | `{"alias":"<field>","param":"form.<field>"}` | **Must use `form.<token>`** when dashboard uses `<form>` inputs — not bare field name |
| Time handling | Hidden `<input type="time" token="tr">` default `-24h@h` → `now` | **Critical:** EH time picker **overrides** panel `<earliest>`/`<latest>` tags. Sparse data (e.g. 15m+ poll interval) shows empty if EH picker is `-15m` |
| Chart/search panels | `<earliest>$tr.earliest$</earliest>` `<latest>$tr.latest$</latest>` | Locks sensible window independent of EH picker override |
| Snapshot panels | `<earliest>0</earliest>` `<latest></latest>` | Inventory / latest-status tables need all-time, not EH window |
| `alias_param_map` scope | **Entity fields only** | Do **not** map `earliest`/`latest` — they are not entity identifiers; causes token binding errors |
| Searches | `depends="$<field>$"` | Avoids dispatch before token populated |
| `dashboard_type` | `xml_dashboard` | Works when above contract is met |

### Entity-type drilldown JSON (example)

```json
{
  "dashboard_drilldowns": [{
    "title": "<Entity Type> Health",
    "id": "<dashboard_id>",
    "base_url": "",
    "dashboard_type": "xml_dashboard",
    "params": {
      "static_params": {},
      "alias_param_map": [
        { "alias": "serial", "param": "form.serial" }
      ]
    }
  }]
}
```

Second identifier example: `{"alias":"networkId","param":"form.networkId"}`.

### REST deploy endpoints

```
POST /servicesNS/nobody/<TA_APP>/data/ui/views          # create dashboard
POST /servicesNS/nobody/<TA_APP>/data/ui/views/<id>/acl # global ACL
POST /servicesNS/nobody/SA-ITOA/itoa_interface/entity_type/<key>?is_partial_data=1
```

Delete duplicate dashboards across owner namespaces (`admin`, named users, `nobody`) and legacy app homes (`itsi`, `search`) before recreate.

### Time override — diagnostic pattern

If an entity has events at `-24h@h` but **none at `-15m``, EH embed is likely passing the parent's narrow time picker into the iframe and overriding panel `<earliest>` tags. Hidden form time token `tr` is the fix.

### Known open issue (defer unless explicitly scoped)

- **Splunk dark UI preference:** Simple XML dashboards and Dashboard Studio embeds render poorly (contrast/layout). Defer; not a token/data issue.

---

## OOTB reference patterns (compare, don't blindly copy)

| Object | App | Root | Tokens | Notes |
|---|---|---|---|---|
| `DA-ITSI-OS-Host_Entity_View` | `itsi` | `<dashboard>` | `$host$`, `$earliest$`, `$latest$` | Custom viz `SA-ITSI-CustomModuleViz.*`; embed-first |
| `host_information` | `DA-ITSI-CP-windows-dashboards` | `<form>` | table-only; empty `alias_param_map` | Snapshot / drilldown helper |
| `ta_nix` entity drilldown | — | — | `udf_dashboard` | Dashboard Studio path when xml embed fails |

**Do not assume one OOTB pattern fits all entity types.** Host-centric `$host$` dashboards differ from TA dashboards with custom identifier fields.

---

## Failure modes & fixes

### 1 — Dashboard "deleted" or not found in embed

| Cause | Fix |
|---|---|
| Private ACL (named owner, no `read=*`) | `owner=nobody`, `sharing=global`, `perms.read=*` |
| Home app `itsi` + `isVisible=False` | Move to TA/CP app; set visibility as needed |
| Duplicate namespaces | Delete stale copies; one canonical `nobody/<TA_APP>` object |

### 2 — Token binding errors (`earliest`, `latest`, entity field)

| Cause | Fix |
|---|---|
| Mapped `earliest`/`latest` in `alias_param_map` | Remove — not entity fields |
| `param: "serial"` with `<form>` input `token="serial"` | Use **`form.serial`** |
| Custom tokens `host_tok`, `tr_tok` | Use ITSI standard names or explicit `form.<name>` |

### 3 — Identifier populates but panels empty

| Cause | Fix |
|---|---|
| EH time picker overrides panel times to narrow window | Hidden `tr` time input; panels use `$tr.earliest$`/`$tr.latest$` |
| Snapshot panel uses EH window | `earliest=0` for inventory/latest-row panels |
| Extra filters exclude entity | Filter on identifier only if entity type already scopes type |

### 4 — Theme / contrast

`theme="dark"` on Simple XML inside EH light chrome → unreadable. Removing theme does **not** fix token/time issues. Splunk **global dark UI preference** also breaks xml/DS embed layout — separate from token contract.

### 5 — Still broken after correct tokens (host-centric dashboards)

If `<dashboard>` + `$host$`/`$earliest$`/`$latest$` still fails: try **`udf_dashboard`** (Dashboard Studio) like `ta_nix`, or clone `DA-ITSI-OS-Host_Entity_View` custom viz + stylesheet. Also try **`form.host`** + hidden `tr` time token before abandoning xml_dashboard.

---

## Agent checklist

```
- [ ] Reproduce in Entity Health (not only /app/<home_app>/<dash>)
- [ ] Confirm home app is TA/CP (not core itsi) and ACL is global nobody
- [ ] Grep alias_param_map: entity fields only; form.<token> if using <form>
- [ ] Grep dashboard XML: hidden tr time token if data is sparse vs EH picker
- [ ] Snapshot panels: earliest=0; metric panels: $tr.earliest$/$tr.latest$
- [ ] Delete duplicate dashboard objects across owner/app namespaces
- [ ] Test with real entity identifier known to have data in chosen time window
- [ ] If still broken: udf_dashboard / custom module viz path
```

## Related skills

- `splunk-itsi-entity-health-dashboard-embed` — narrower case studies (host vs non-host embed outcomes)
- `splunk-itsi-common-errors` — ambient stack errors (`wineventlog-ds`, `LOOKUP-dropdowns`)
- `splunk-itsi-api-access` — REST tokens and endpoints
- `splunk-itsi-kpi-creation-via-api` — `vital_metrics` on same entity types

## Chronology lessons (avoid repeat trial-and-error)

| Attempt | Change | Result |
|---|---|---|
| v1 | Dashboard in `itsi`, private ACL | "Deleted" / not found in embed |
| v2 | Global ACL, still `itsi` home | Not discoverable; wrong app context |
| v3 | Moved to TA/CP app, `isVisible=True` | Found in UI; embed loads |
| v4 | Mapped `earliest`/`latest` in `alias_param_map` | Token binding errors |
| v5 | `param: serial` (no `form.` prefix) | Identifier not bound in form |
| v6 | `$earliest$`/`$latest$` on panels | EH picker overrode to `-15m`; empty charts |
| **v7** | `<form>` + `form.<field>` + hidden `tr` token | **Works** when data exists in `tr` window |
