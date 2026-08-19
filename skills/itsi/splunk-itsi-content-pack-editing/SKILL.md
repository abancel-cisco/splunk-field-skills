---
name: splunk-itsi-content-pack-editing
category: itsi
description: Do's and don'ts for editing, versioning, and removing custom ITSI content packs (the ITSI Authored Content wizard + the installed app + the KV objects it stamps). Covers object ownership rules (never attach the same object to two content packs), why authorship is not portable between Splunk instances (server_guid), what the wizard regenerates/wipes on every build, why modular inputs must ship in a separate TA, preferring pack-owned uniquely-named macros over depending on another pack, and the two-layer removal (app + source_itsi_da-stamped KV objects + status record + authorship draft). Use when authoring/editing/rebuilding/removing an ITSI content pack, choosing what objects to include in the wizard, resolving cross-pack object ownership or macro conflicts, migrating a pack between stacks (e.g. Acme -> a lab instance), or cleaning up a previously installed/imported pack.
disable-model-invocation: true
---

# Editing ITSI Content Packs — do's & don'ts

An ITSI content pack has **three** moving parts. Most mistakes come from confusing them:

| Part | What it is | Lives in |
|---|---|---|
| **Authoring draft** | The wizard's selection of objects to package | `itsi_content_pack_authorship` KV collection, on the **authoring** stack only |
| **Installed app** | `DA-ITSI-CP-CUST-<key>` (or your id) app with `itsi/manifest.json` + `default/` | `$SPLUNK_HOME/etc/apps/` |
| **Installed objects** | Services, KPIs, base searches, entity types, etc. copied into KV on Install | ITSI KV store, stamped `source_itsi_da*` |

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## Golden rules (don'ts)

- **Never attach the same object to two content packs.** An installed object is stamped with a
  single `source_itsi_da` (+ `_id`, `_version`). Two packs claiming the same object fight over
  ownership; uninstalling one can delete or orphan the object for the other. For app-level conf
  objects (macros, saved searches), two apps defining the **same stanza name** also collide via
  conf layering. Ship your **own uniquely-named** copy, or **reference** the shared object
  without including it.
- **Don't depend on another pack's knowledge objects if you can own them.** Prefer a pack-owned,
  uniquely-named macro (e.g. `mypack_metrics_indexes = index=sim_metrics`) over referencing
  another pack's macro — it removes the dependency and any ownership conflict. Referencing is
  fine only for a stable prerequisite you deliberately require.
- **Don't expect to edit/rebuild a pack authored on another stack.** The built tarball records
  the authoring Search Head's `server_guid`; download/rebuild is rejected elsewhere, and the
  authoring draft lives only in that stack's KV. To iterate on a different instance, create a
  **new** authoring record there.
- **Don't hand-edit the wizard's staged app dir.** Every Build `rmtree`s and regenerates
  `$SPLUNK_HOME/var/itsi/content_pack/<key>/DA-ITSI-CP-CUST-<key>/`. Hand-added files are wiped.
- **Don't try to package modular inputs in the wizard.** It can't select them. Ship data
  collection (e.g. SIM `sim_modular_input` stanzas) in a **separate TA**, not the pack.
- **Don't assume Splunk objects are auto-included.** Dashboards, saved searches, and macros must
  be **explicitly selected** in the wizard's *Splunk objects* step. Only ITSI objects (and their
  direct ITSI dependencies) come along automatically.

## Do

- **Treat the authoring KV record as source of truth** for what a pack contains. Inspect
  `itsi_content_pack_authorship` and read `itsi_objects` + `splunk_objects`.
- **Give the pack its own app id and stable object `_key`s.** Re-installing with the same keys
  overwrites in place (an upgrade); changing keys/title-prefix creates duplicates.
- **Deliver SIM/O11y inputs as a companion TA** with disabled stanzas + SignalFlow baked in;
  operator sets `org_id` (blank = SIM default account) and enables.
- **Document prerequisites explicitly** (e.g. `splunk_ta_sim`), and drop optional deps you
  replaced with pack-owned objects.

## Audit what a pack owns (REST)

`| rest` is GET-only and often blocked; use splunkd REST directly. Installed objects filter by
`source_itsi_da`:

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$SH/servicesNS/nobody/SA-ITOA/itoa_interface/service?filter=$(python3 -c 'import urllib.parse,json;print(urllib.parse.quote(json.dumps({"source_itsi_da":"<pack id>"})))')&fields=_key,title,source_itsi_da"
```
Repeat for `kpi_base_search`, `base_service_template`, `entity_type`, etc. The authoring draft:
`.../SA-ITOA/storage/collections/data/itsi_content_pack_authorship`.

## Removing a pack (two layers, reverse dependency order)

Removing the app does **not** delete installed objects. Remove in this order:

1. **Installed KV objects** stamped with the pack's `source_itsi_da` — delete in reverse
   dependency order: rollup/parent service → leaf services → templates → KPI base searches →
   entity types → import saved searches → dashboards → (optionally) imported entities.
2. **Status record** in the `itsi_content_pack_status` KV collection.
3. **The app** (`etc/apps/<pack id>`), then reload/restart.
4. **Authoring draft** (only on the authoring stack): delete from the Authored Content UI.

**Safe uninstall when objects are shared or load-bearing:** instead of deleting, **clear**
`source_itsi_da` / `source_itsi_da_id` / `source_itsi_da_version` on those objects (re-own them
as ad-hoc, or let another live pack keep them), then remove the app + status record. This avoids
breaking live services. Back up first (Configuration → Backup/Restore).

## Migrating a pack between stacks

The tarball is not editable off its origin stack. To move DBM-style content from stack A to B:
deploy/import the objects on B, then create a **fresh** authoring record on B and rebuild there.
Objects on B are independent knowledge objects — editable normally; only the *authorship* is
stack-bound.

## Imported → authored migration (imported pack → editable local pack)

Downloading an imported content pack and *re-authoring* it locally so it's editable/buildable is not
officially supported but works. The authored pack is nothing more than an
`itsi_content_pack_authorship` KV record whose `server_guid` == the local stack, referencing KV
objects by `_key`. Recipe (see `DA-ITSI-CP-sim-os-hosts/scripts/generate_sim_os_hosts.py`):

1. **Materialize objects** in KV via `itoa_interface` with your own `_key`s (POST to create,
   `POST .../<obj>/<key>?is_partial_data=0` to replace). Objects: `kpi_base_search`,
   `entity_type`, `service`, `base_service_template`; import searches via `saved/searches` in
   `SA-ITOA`; the index macro via `configs/conf-macros` (share global).
2. **Write the authorship record** to `storage/collections/data/itsi_content_pack_authorship`
   with `server_guid` = local (`server/info` → `guid`), `status:"Generated"`,
   `authorship_progress.stage:"STAGE_BUILD_COMPLETE"`, and `itsi_objects`/`splunk_objects`/
   `user_selected_objects` listing your keys (mirror an existing record's shape exactly).
3. The pack now appears under **Authored**; open → edit → **Build/Export** for the tarball.
   (The Build step is a UI controller; there is no clean documented REST build endpoint — don't
   reverse-engineer it, click Build.)

### itoa_interface gotchas learned the hard way

- **KPI `_key`s must be globally unique across services.** Two services reusing the same KPI
  keys → HTTP 400 *"KPI keys are not unique"*. Namespace them (e.g. `sim_linux_*`/`sim_windows_*`).
- **Service templates cannot filter KPIs to service entities.** Setting
  `is_filter_entities_to_service`/`is_service_entity_filter` = true on a `base_service_template`
  KPI → HTTP 400 *"Cannot filter on entities … if there are no entities"*. Build template KPIs
  with those `false`; set them `true` only on the real service's KPIs.
- **A KPI base search metric can't be dropped once a template uses it.** Re-PATCHing the base
  search with the same `metrics` is rejected (*"metric … used by one or more service templates"*).
  Create the base search once; skip re-patching metrics if it already exists.
- **`configs/conf-*` endpoints return XML, not JSON** — don't blindly `json.loads` the response.
- **Split-by-OS pattern:** one shared base search (`by host.name`); per-OS entity types; import
  searches filter `os.type=<os>` and set an `etype` info field; services match `etype` in
  `entity_rules`. OS host metrics for identity/discovery live on `memory.utilization` (carries
  `os.type`), not `cpu.utilization`.
