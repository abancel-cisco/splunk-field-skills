---
name: splunk-itsi-entity-health-dashboards
category: itsi
description: Documents how ITSI Entity Health embeds custom dashboards on entity_type.dashboard_drilldowns. The default is Dashboard Studio as udf_dashboard, the ITSI 5.0 contract that every shipped pack uses. It has no inputs, a bare entity token, and the reserved time_range_token alias mapped to global_time. On 5.0 the Simple XML form.<token> pattern shows "Search is waiting for input...". Also covers light/dark colour-mode rules, the legacy Simple XML xml_dashboard contract validated on ITSI 4.21.x Cloud, and why dashboards often fail only inside the embed. Covers form vs dashboard XML, form.<token> alias_param_map for non-host identifiers, hidden tr time token when EH overrides panel earliest/latest, home app in TA/CP not itsi, global ACL owner=nobody, reference patterns DA-ITSI-OS-Host_Entity_View and host_information. Use when custom entity dashboards break only in Entity Management or Entity Health, when wiring dashboard_drilldowns on custom entity types, or when building TA/CP entity views.
disable-model-invocation: true
---

# ITSI Entity Health — Custom Dashboard Embed

How ITSI **Entity Health** loads custom dashboards, why they often **fail only in the embed**, and the **validated contract** for non-host entity identifiers on ITSI 4.21.x / Splunk Cloud.

**Validated on:** ITSI 4.21.x, Splunk Cloud (multiple stacks) for the Simple XML pattern. ITSI 5.0.2 on-prem for the Dashboard Studio contract below, which comes first because it is the default.

## Default: Dashboard Studio (`udf_dashboard`) — the ITSI 5.0 contract

**Prefer Dashboard Studio for every new entity dashboard.** On 5.0, the Simple XML `<form>` + `form.<token>` pattern described further down binds no token inside Entity Health. Every panel then shows **"Search is waiting for input..."**. This was reproduced on 5.0.2. Every shipped pack with an entity dashboard uses the contract below: Cisco Enterprise Networks, Cisco Data Center, AppDynamics and ThousandEyes.

| Piece | Value |
|---|---|
| Root | `<dashboard version="2" theme="light">` with the JSON definition in `<definition><![CDATA[ … ]]>` |
| Inputs | **None.** `"inputs": {}` and `"layout": {"globalInputs": []}`. ITSI sets the tokens itself |
| Entity token | A bare token name (e.g. `entity_token`) used directly in queries: `host="$entity_token$"` |
| Time | `defaults.dataSources["ds.search"].options.queryParameters` = `{"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}` |
| `dashboard_type` | `udf_dashboard` |
| `alias_param_map` | `{"alias": "<entity alias>", "ds_source": "", "param": "entity_token"}` plus `{"alias": "time_range_token", "ds_source": "", "param": "global_time"}`. `time_range_token` is a reserved alias for the Entity Health time range; shipped packs use `time_range_token`, `time_range_token-1`, `-2` or `-4` interchangeably. **No `form.` prefix** |
| Home app / ACL | As for Simple XML: the pack's app, `owner=nobody`, global, `read=*` |

```json
"dashboard_drilldowns": [{
  "title": "<Entity Type> Health", "id": "<view_id>", "base_url": "",
  "dashboard_type": "udf_dashboard",
  "params": {"static_params": {}, "alias_param_map": [
    {"alias": "<entity alias>", "ds_source": "", "param": "entity_token"},
    {"alias": "time_range_token", "ds_source": "", "param": "global_time"}]}
}]
```

**Colour mode.** Entity Health embeds render wrongly in one of the two modes more often than not. Rules:
- Set `theme="light"`, as every shipped pack does.
- **Never hardcode colours.** That means no `backgroundColor`, no series colours and no `majorColor`. A hardcoded background is what turns a panel unreadable once a user's preference is dark.
- Check every new dashboard with the user's preference in both light and dark.

The Simple XML material below still applies to 4.21 stacks, and to repairing older dashboards.

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

## Legacy pattern — non-host identifier + `<form>` (ITSI 4.21.x only; fails on 5.0)

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
- [ ] ITSI 5.0: Dashboard Studio + udf_dashboard, no inputs, bare token, time_range_token -> global_time
- [ ] theme="light", no hardcoded colours; check light and dark user preference
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
| **v7** | `<form>` + `form.<field>` + hidden `tr` token | **Works** when data exists in `tr` window (4.21) |
| v8 (5.0.2) | Same v7 dashboard on ITSI 5.0 | "Search is waiting for input..." on every panel |
| **v9 (5.0.2)** | Dashboard Studio, no inputs, `udf_dashboard`, bare `entity_token` + `time_range_token` → `global_time` | The contract every shipped 5.0 pack uses |
