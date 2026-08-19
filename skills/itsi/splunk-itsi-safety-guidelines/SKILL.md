---
name: splunk-itsi-safety-guidelines
category: itsi
description: Safety guidelines and development rules for Splunk ITSI agents. Prohibits direct modification of core system macros (e.g., itsi_notable_group_lookup) and rules-engine components to prevent head-of-line blocking, thread starvation, and search head outages. Promotes ingestion-time enrichment (Correlation Search) over action-time execution.
disable-model-invocation: true
---

# Splunk ITSI Agent Safety and Development Guidelines

This document provides safety constraints and best practices for agents modifying ITSI (IT Service Intelligence) environments. Follow these rules to avoid causing search head outages, KV store queue exhaustion, and NEAP (Notable Event Aggregation Policy) failures.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## 1. Safety Constraints (Prohibited Modifications)

> [!CAUTION]
> **Never modify core/system-level ITSI macros or configuration files directly.**
>
> Doing so can affect the critical path of the ITSI rules engine, leading to system-wide failures.

Specific restrictions:
*   **Do not edit the `itsi_notable_group_lookup` macro.** This macro is executed dynamically via `earemotesearch` for every notable event action dispatch. Modifying it with joins, subsearches, or slow lookups causes cascading timeouts and exhausts queue consumer threads (`notable_event_actions_queue_consumer`).
*   **Do not modify configuration stanzas or configs** under `SA-ITOA` that are used by the rules engine or KV store consumers without explicit, multi-peer review and offline validation.

## 1a. Never edit stock / out-of-the-box content — clone instead

> [!CAUTION]
> Never directly modify shipped ("stock"/OOTB) ITSI content: correlation searches, Notable Event Aggregation Policies (NEAPs), KPI/service base-search templates, entity types, saved searches, macros, or dashboards that ship with ITSI or a Content Pack.

Reasons:
- **Upgrades overwrite stock objects**, silently reverting your change (and any behavior that depended on it).
- Stock objects are usually **shared across every service/team** on the stack, so an edit intended for one use case leaks everywhere (e.g. repointing the single URL drilldown on `Service Monitoring - Entity Degraded` changes it for *all* services).

Required workflow to customize stock behavior:
1. **Clone** the stock object (new unique title/`_key`, owner `nobody`, correct app).
2. **Edit the clone** only.
3. **Verify** the clone works (dispatch it / generate an episode / render the drilldown).
4. **Disable the original** *only if the clone must replace it* (`disabled=1`) — never delete stock. If the clone is **additive** (a scoped NEAP with higher `priority`, or a brand-new correlation search), leave the original enabled and rely on scoping/priority instead.

NEAP specifics:
- Create a **new scoped policy** (tight `filter_criteria`, `priority` higher than the default catch-all which is `priority=5`, `is_default=1`) rather than editing `Default Policy` or any shipped policy.
- Put episode-integrated drilldowns/dashboards in the clone's **`group_dashboard`** (inline Dashboard Studio JSON) + **`group_dashboard_context`** (`"first"`/`"last"` selects which notable's fields populate tokens, e.g. `$entity_title$`, `$itsi_group_id$`). This is the supported way to surface a custom dashboard as a tab inside an episode — including for **pseudo-entities** (split-by-field values that carry `entity_title` but have `entity_key=N/A` / `is_entity_defined=0`).

## 2. Ingestion-Time vs. Action-Time Enrichment

To enrich Notable Event or Episode webhooks with CMDB fields (such as `assignedgroupID` or location details):
*   **Prohibited (Action-time):** Modifying macro definitions or adding heavy lookup subsearches inside the Action rule evaluation. This hangs the rules engine queue.
*   **Required (Ingestion-time):** Perform the lookups directly in the **Correlation Search (CS)** that generates the notable events:
    ```spl
    index=your_index sourcetype=your_sourcetype
    | lookup cmdb_lookup host AS src_host OUTPUT assignedgroupID
    | ...
    ```
    ITSI automatically replicates notable event fields into parent episodes. The webhook alert action can then directly reference the pre-enriched field without executing any subsearches.

## 3. Network & Outbound Proxy Considerations

*   Before proposing alert webhooks or custom command executions, verify search head egress proxy configurations.
*   If a proxy is configured, confirm that local REST calls to external hostnames on port `8089` are added to the `NO_PROXY` environment variable in `splunk-launch.conf` or bypass the proxy to prevent command timeouts (e.g., `earemotesearch` `ProxyError`).
