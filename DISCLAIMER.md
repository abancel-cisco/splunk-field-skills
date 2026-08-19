# Disclaimer

## Not an official project

This repository is **not an official Splunk or Cisco project**, and is not affiliated
with, sponsored by, or endorsed by either company. It is maintained personally.

The contents are field notes: patterns worked out during real Splunk implementations
and written down so an AI agent can repeat them. They have **not been reviewed or
blessed by Splunk product management**, and nothing here should be read as a statement
of product direction, a commitment, or a recommended practice sanctioned by the vendor.

Where a skill disagrees with the official Splunk documentation, the official
documentation is correct and this repository is out of date.

## No support

These skills are **not covered by any Splunk support contract**. Splunk Support cases
cannot help with them, and raising one about a skill in this repository will waste your
time and theirs. See [SUPPORT.md](SUPPORT.md).

## Version-bound accuracy

Every skill states the product versions it was validated against, inline near the top.
The baseline across this repository is **Splunk ITSI 4.21.x**, with a subset re-validated
on **ITSI 5.0.x** and **Splunk Enterprise 10.4.x**; skills that were not re-verified on
5.0 say so explicitly.

ITSI and the Splunk platform change materially between releases — REST payload shapes,
KV store object schemas, wizard behaviour, and default app permissions have all shifted
within the range these skills cover. A skill validated on ITSI 4.21 may be wrong on 5.0,
and vice versa. Check the version note in the skill before trusting it, and re-verify
in a lab if your version is not listed.

## These skills change your Splunk environment

This is the most important item on the page.

A meaningful number of these skills instruct an agent to **write** to a Splunk or ITSI
instance over the REST API. Between them they create and modify services, KPIs, entities,
entity types, glass tables, dashboards, correlation searches, notable event aggregation
policies, KV store collections, and content pack apps. Some describe deletion and cleanup
procedures.

An agent following one of these skills can therefore change, degrade, or break a live
service-monitoring environment, including one your organisation depends on for
production alerting.

Accordingly:

- **Run against a lab or non-production stack first.** Always, including for skills that
  look read-only.
- **Read the skill before you invoke it.** Do not let an agent execute a skill you have
  not looked at. They are plain Markdown and take a few minutes to read.
- **Use a least-privilege token.** Do not hand an agent an admin token because it is
  convenient. `splunk-itsi-api-access` documents the specific capabilities each task needs.
- **Take a backup first** where the skill involves content packs, KV store objects, or
  bulk KPI changes.
- **Review what the agent proposes** before it applies anything, particularly for bulk
  operations across many services.

[`splunk-itsi-safety-guidelines`](skills/itsi/splunk-itsi-safety-guidelines/SKILL.md)
covers the operations that are genuinely dangerous on a live ITSI search head — modifying
core system macros and rules-engine components can cause head-of-line blocking and take
the search head out. Read it before anything else in this repository.

## No warranty

This work is provided under the [Apache License 2.0](LICENSE), without warranty or
condition of any kind, express or implied. You are responsible for what you run against
your own environments and your customers'.
