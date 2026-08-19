# Splunk Field Skills

Agent skills for Splunk IT Service Intelligence, the Splunk platform, and Splunk
Observability Cloud — written by a sales engineer, from real implementation work.

> [!WARNING]
> **This is not an official Splunk or Cisco project.** These skills have not been
> reviewed or endorsed by Splunk product management, and they are not covered by
> any Splunk support contract. Several of them perform **write operations** against
> live ITSI stacks. Read [DISCLAIMER.md](DISCLAIMER.md) before using them.

Each skill is a single `SKILL.md` describing a task an AI coding agent can carry out
against a Splunk environment: creating a service tree over REST, binding entities to
KPIs, authoring a content pack, diagnosing a saturated search head. They encode the
order of operations, the payload shapes, and the failure modes — the parts that are
not in the product documentation because they only show up in the field.

## Compatibility baseline

The baseline is **Splunk ITSI 4.21.x**, with a subset re-validated on **ITSI 5.0.x** and
**Splunk Enterprise 10.4.x**. Every skill states its own validation status near the top,
and says so explicitly where it has not been re-verified on 5.0. ITSI's REST surface and
UI change meaningfully between releases, so treat a skill as accurate for the version it
names and unverified everywhere else.

## Install

The repository uses the `skills/<category>/<name>/SKILL.md` catalog layout, which the
[`skills` CLI](https://github.com/vercel-labs/skills) discovers without extra flags.

```bash
# see what's here
npx skills add abancel-cisco/splunk-field-skills --list

# install everything for your agent
npx skills add abancel-cisco/splunk-field-skills --skill '*' --agent cursor --copy --yes

# or install one skill
npx skills add abancel-cisco/splunk-field-skills --skill splunk-itsi-service-tree-design --agent cursor --copy --yes
```

Swap `--agent` for `claude-code`, `codex`, `github-copilot`, `gemini-cli`, or
`opencode`. Add `--global` to install at user level instead of per-project.

To install manually, copy the directory you want out of `skills/` into your agent's
skills directory.

## Skills

### `itsi/` — Splunk IT Service Intelligence

| Skill | Purpose |
|---|---|
| [`splunk-itsi-api-access`](skills/itsi/splunk-itsi-api-access/SKILL.md) | Reach an ITSI search head over REST: token shapes, required capabilities, IP allowlisting, 401 triage, proxy egress. |
| [`splunk-itsi-safety-guidelines`](skills/itsi/splunk-itsi-safety-guidelines/SKILL.md) | Rules for agents operating on a live ITSI stack — what never to modify, and why. **Read this first.** |
| [`splunk-itsi-service-tree-design`](skills/itsi/splunk-itsi-service-tree-design/SKILL.md) | Design and build a service tree over REST without disturbing existing customer content. |
| [`splunk-itsi-entity-binding-architecture`](skills/itsi/splunk-itsi-entity-binding-architecture/SKILL.md) | The four-layer chain that makes KPIs actually scope to the right entities under a service. |
| [`splunk-itsi-entity-cmdb-lookup`](skills/itsi/splunk-itsi-entity-cmdb-lookup/SKILL.md) | Build a CSV-based mini-CMDB to enrich entities with business context machine data can't supply. |
| [`splunk-itsi-kpi-creation-via-api`](skills/itsi/splunk-itsi-kpi-creation-via-api/SKILL.md) | Create and modify KPIs at scale over REST — clone a working KPI to N services, switch metrics in a shared base search. |
| [`splunk-itsi-flow-monitoring`](skills/itsi/splunk-itsi-flow-monitoring/SKILL.md) | Model a multi-step transaction or integration flow as services with KPIs, for bottleneck and cycle-time detection. |
| [`splunk-itsi-content-pack-creation`](skills/itsi/splunk-itsi-content-pack-creation/SKILL.md) | Author a custom content pack from scratch through the ITSI wizard, end to end. |
| [`splunk-itsi-content-pack-editing`](skills/itsi/splunk-itsi-content-pack-editing/SKILL.md) | Edit, version, and remove content packs — object ownership rules, what the wizard wipes on rebuild, two-layer removal. |
| [`splunk-itsi-glass-table-rest`](skills/itsi/splunk-itsi-glass-table-rest/SKILL.md) | Create glass tables over REST, with service health score tiles on a custom backdrop. |
| [`splunk-itsi-entity-health-dashboards`](skills/itsi/splunk-itsi-entity-health-dashboards/SKILL.md) | Embed custom Simple XML dashboards as entity-type drilldowns: the token, time, ACL, and app contract. |
| [`splunk-itsi-entity-health-dashboard-embed`](skills/itsi/splunk-itsi-entity-health-dashboard-embed/SKILL.md) | Case studies of embed failures, and the pattern that actually works. |
| [`splunk-itsi-bidirectional-ticketing`](skills/itsi/splunk-itsi-bidirectional-ticketing/SKILL.md) | Integrate third-party ticketing gateways with episodes, with REST payloads. |
| [`splunk-itsi-hybrid-action-dispatching`](skills/itsi/splunk-itsi-hybrid-action-dispatching/SKILL.md) | Configure and troubleshoot notable-event action dispatch between a cloud manager node and an on-prem executor. |
| [`splunk-itsi-performance-tuning`](skills/itsi/splunk-itsi-performance-tuning/SKILL.md) | Diagnose the saturated-scheduler class of problems: skipped searches, KPIs going N/A under load. |
| [`splunk-itsi-common-errors`](skills/itsi/splunk-itsi-common-errors/SKILL.md) | Five recurring ITSI errors with root cause and fix, including the "Backfill the KPI" message that backfilling won't fix. |
| [`splunk-itsi-static-data-replay`](skills/itsi/splunk-itsi-static-data-replay/SKILL.md) | Make static or historical data appear live to KPIs, via a single centralised macro. |
| [`splunk-itsi-50-release-overview`](skills/itsi/splunk-itsi-50-release-overview/SKILL.md) | What changed in ITSI 5.0 across Service Insights, Event Analytics, and Data Integrations. |
| [`splunk-itsi-50-upgrade`](skills/itsi/splunk-itsi-50-upgrade/SKILL.md) | Upgrade to ITSI 5.0 on single-instance or distributed on-prem. |

### `platform/` — Splunk platform

| Skill | Purpose |
|---|---|
| [`splunk-dashboard-studio-rest`](skills/platform/splunk-dashboard-studio-rest/SKILL.md) | Create Dashboard Studio (v2) dashboards programmatically through the `data/ui/views` REST endpoint. |

### `observability/` — Splunk Observability Cloud

| Skill | Purpose |
|---|---|
| [`otel-vs-splunk-ingestion`](skills/observability/otel-vs-splunk-ingestion/SKILL.md) | Decide between the OTel Collector and the Universal Forwarder for a given data source. |

### `_meta/`

| Skill | Purpose |
|---|---|
| [`external-knowledge-sources`](skills/_meta/external-knowledge-sources/SKILL.md) | Live pointers to external, actively maintained Splunk skill and SPL catalogs. See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md). |

## Scope

This repository covers implementation craft for Splunk products: how to build a thing
correctly, and how to recognise it when it breaks. It deliberately excludes sales
methodology, engagement process, and anything specific to how a particular vendor or
partner organisation runs its business.

Skills are written against supported, documented interfaces — the REST API, the ITSI
authoring wizards, configuration files. Where a task can only be done through a UI
surface with no API behind it, the skill says so rather than inventing a workaround.

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) — the important
rules are that contributions must carry no customer-identifying information, and that
every skill states the product versions it was validated against.

## Policies

- [Disclaimer](DISCLAIMER.md) — what this is and is not
- [Support](SUPPORT.md) — there isn't any, and what to do instead
- [Security](SECURITY.md) — how to report a problem
- [Acknowledgements](ACKNOWLEDGEMENTS.md) — external sources this work builds on
- [Apache License 2.0](LICENSE)
