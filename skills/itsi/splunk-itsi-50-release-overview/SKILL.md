---
name: splunk-itsi-50-release-overview
category: itsi
description: Catalogs Splunk IT Service Intelligence 5.0 new features and behavioral changes across Service Insights, Event Analytics, and Data Integrations — cross-team service/episode sharing with NEAPs and fine-grained RBAC, structured service/KPI tagging, ITSI Admin Console, recurring and ServiceNow-synced maintenance windows, Event iQ Detect/Diagnose AI episode analysis, Episode Review UX overhaul, aggregation-policy priority, Default CMDB CI Enrichment Policy, modernized Content Library, and new alert integrations (Dynatrace, Zabbix, Oracle Enterprise Manager, Datadog). Use when planning ITSI 5.0 projects, demos, upgrade validation, feature walkthroughs, or when the user mentions ITSI 5.0 / Event iQ / cross-team episodes / NEAP sharing / ITSI Admin Console / aggregation policy priority.
disable-model-invocation: true
---

# Splunk ITSI 5.0 — Release Overview

Feature catalog for **ITSI 5.0** (released 2026-06-30). Use this skill to plan demos, validate upgrades, and decide which new capabilities to exercise on a lab or dev instance.

**Docs:** [New features in ITSI 5.0](https://help.splunk.com/en/splunk-it-service-intelligence/splunk-it-service-intelligence/release-notes-and-resources/5.0/release-notes/new-features-in-splunk-it-service-intelligence)

## Version context

| Area | ITSI 4.21.x (prior lab baseline) | ITSI 5.0 |
|------|----------------------------------|----------|
| Cross-team services/episodes | Limited team isolation | Owner team + shared teams; NEAP cross-team episode sharing |
| Episode actions | `execute_notable_event_action` | Four fine-grained capabilities |
| Maintenance windows | Basic scheduling | Recurring, multi-day, clone, extend to external CIs, ServiceNow import |
| Service metadata | Limited | Structured key-value tags on services, templates, sandbox services |
| Event triage | Classic Episode Review | Event iQ Detect + Diagnose; redesigned Episode Review |
| Alert aggregation | First-match implicit order | Explicit priority on NEAPs (descending; first match wins) |
| Data integrations | Prior set | + Dynatrace, Zabbix, Oracle EM, Datadog |
| Admin UX | Scattered config | ITSI Admin Console / Advanced Configuration page |

## Service Insights

### Cross-team RBAC (services and episodes)

- Services and episodes (via **NEAPs**) can be **shared across teams**.
- Cross-team **service dependencies** — shared services can be dependencies in services owned by other teams.
- Episodes carry an explicit **owner team**.
- **Fine-grained capabilities** govern mutating episode actions (replaces `execute_notable_event_action`).
- Shared teams get **read-only** access; owner team retains control.
- Team-scoped episode filtering and assignee picker.
- Logic retained across Service Analyzer, Health Score, Glass Tables, Deep Dive, KPI base-search dependents.

**Lab demo ideas:** Create two teams; share a service; verify dependency wiring and episode visibility boundaries.

**Docs:** Share a service to a different team; Sharing episodes with other teams using NEAPs; Take action on an episode.

### Service and KPI tagging

- Structured **key-value tags** on services, service templates, and service sandbox services.
- Use for inventory search, organization, and governance at scale.

**Docs:** Add tags to a service in ITSI.

### Maintenance windows

- **Recurring** maintenance windows (advanced scheduling).
- **Clone** existing windows; **multi-day** windows.
- Extend maintenance to **external configuration items (CIs)**.
- **ServiceNow sync** — import maintenance schedules/outages to reduce manual config and false positives.

**Docs:** Schedule maintenance downtime in ITSI; Import external maintenance windows; Import a maintenance window from ServiceNow.

### Backup and restore

- Partial backups now account for **team structure** — dependent services and teams auto-selected.

**Docs:** Create a partial backup.

### ITSI Admin Console

- Centralized admin settings in the UI (Advanced Configuration page).

**Docs:** Use the ITSI Advanced Configuration page.

## Event Analytics

### Event iQ Detect and Diagnose

- **AI episode summarization**, troubleshooting insights, and root-cause analysis.
- Recommendations for high-quality **grouping fields** for alert correlation into episodes.
- Bridges detection → resolution with context-rich insights.

**Docs:** Automate event correlation with Event iQ Detect; Use Event iQ Diagnose to analyze episodes with AI.

### Episode Review overhaul

- Modernized layout for faster triage.
- **Custom tabs** aligned to team workflows.
- Advanced filtering.
- **AI-generated insights** on episode selection.
- Enhanced summaries: affected services, suspected root cause, relevant log trends.

**Docs:** Investigate episodes in ITSI; Customize Episode Review in ITSI.

### Flexible alert aggregation

- **Priority value** on notable event aggregation policies (NEAPs).
- ITSI evaluates policies in **descending priority**; stops at first match — one episode per alert.

**Docs:** Configure priority for aggregation policies in ITSI.

### Alert enrichment

- **Default CMDB CI Enrichment Policy** — apply to any data integration connection for richer alert context.

**Docs:** Overview of enrichment policies in ITSI.

## Data integrations

### New monitoring platform integrations

Pre-built field mappings normalize third-party alerts into ITSI's unified alert format:

| Platform | Notes |
|----------|-------|
| Dynatrace | Alert ingestion |
| Zabbix | Alert ingestion |
| Oracle Enterprise Manager | Alert ingestion |
| Datadog | Alert ingestion |

**Docs:** Available data integrations in ITSI.

### Content Library

- Modernized UI for content pack **installation and upgrades**.

**Docs:** Overview of content pack management in ITSI.

## Skills that still apply on 5.0

These pre-5.0 skills remain relevant; verify behavior after upgrade:

| Skill | Still relevant because |
|-------|------------------------|
| `splunk-itsi-api-access` | REST patterns unchanged; test token caps after RBAC changes |
| `splunk-itsi-service-tree-design` | Service tree API; cross-team refs now first-class |
| `splunk-itsi-kpi-creation-via-api` | KPI REST; tagging is additive |
| `splunk-itsi-entity-binding-architecture` | Entity scoping unchanged |
| `splunk-itsi-safety-guidelines` | Rules engine safety still critical |
| `splunk-itsi-common-errors` | §1 wineventlog-ds and §2 LOOKUP-dropdowns validated on 5.0; §3 threshold AI not re-tested |

## Agent checklist — planning ITSI 5.0 work

```
- [ ] Confirm Splunk Enterprise version compatibility (matrix)
- [ ] Read known issues / removed features in 5.0 release notes
- [ ] Identify which feature pillars to demo (Service Insights vs Event Analytics vs Integrations)
- [ ] For cross-team RBAC demos: provision ≥2 teams and test users before content work
- [ ] For Event iQ: ensure AI prerequisites (Splunk AI Toolkit version per matrix)
- [ ] For integrations: pick one platform (lab has Zabbix CP in Stuff/) and map alert fields
- [ ] After upgrade: smoke-test REST, Episode Review, one service dependency, one NEAP
```
