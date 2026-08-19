# Acknowledgements

This repository builds on work maintained by others. Where those sources are actively
updated, the skills here **point at them rather than copying them**, so that agents fetch
the current version instead of a snapshot that quietly goes stale. That mechanism lives in
[`skills/_meta/external-knowledge-sources`](skills/_meta/external-knowledge-sources/SKILL.md).

## External sources

### [`chambear2809/splunk-cisco-skills`](https://github.com/chambear2809/splunk-cisco-skills)

A large, actively maintained catalogue of operational setup and automation skills covering
Splunk platform and Cloud administration, Cisco product onboarding, AppDynamics,
ThousandEyes, collectors, and adjacent workflows.

Where this repository covers ITSI *content design* — service trees, KPIs, entity binding —
that one covers the *setup and automation* layer underneath. They complement each other,
and it is the better starting point for install and configuration tasks. It also served as
the structural model for this repository's layout.

### [`fenre/splunk-monitoring-use-cases`](https://fenre.github.io/splunk-monitoring-use-cases/)

A catalogue of ready-made Splunk monitoring use cases: SPL searches, CIM-aligned
detections, and KPI base searches organised by technology domain. Useful when you need a
starting query for a KPI rather than a way to wire one up.

Machine-readable index: <https://fenre.github.io/splunk-monitoring-use-cases/llms.txt>

### [`splunk/splunk-agent-skills`](https://github.com/splunk/splunk-agent-skills)

Splunk's own experimental agent skills repository. This repository's support and security
statements were modelled on theirs. Note that theirs is published by Splunk and this one is
not — see [DISCLAIMER.md](DISCLAIMER.md).

## Standards and tooling

- The [Agent Skills specification](https://agentskills.io/specification), which defines the
  `SKILL.md` contract these skills implement.
- The [`skills` CLI](https://github.com/vercel-labs/skills), which handles discovery and
  installation across agents.

## Trademarks

Splunk, Splunk IT Service Intelligence, and Splunk Observability Cloud are trademarks of
Splunk LLC. Cisco is a trademark of Cisco Systems, Inc. Used here for identification only;
this repository is not affiliated with or endorsed by either.
