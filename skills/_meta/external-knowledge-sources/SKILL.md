---
name: external-knowledge-sources
category: _meta
description: >-
  Registry of three external, actively-maintained knowledge sources this library references
  live by pointer and never copies: chambear2809/splunk-cisco-skills for Splunk and Cisco
  product setup and automation (install and config, Cloud ACS, HEC, OTel and SC4S collectors,
  Enterprise Security, ITSI install, Observability Cloud, AppDynamics, ThousandEyes); fenre
  splunk-monitoring-use-cases for 7900+ monitoring use cases with SPL and CIM mappings across
  23 technology domains; and splunk/splunk-agent-skills for the vendor's own read-only
  advisory skills (search performance, upgrade readiness, HEC, forwarder fleets, CIM mapping,
  Cloud ACS). Use when a task needs product setup automation, ready-made monitoring or
  detection SPL, or vendor-authored diagnosis beyond what this library covers. Always fetch
  the live URLs at use time rather than a cached snapshot; all three change often, and one
  reshaped its whole skill set twice in a month.
disable-model-invocation: true
---

# External Knowledge Sources

This library is the team's **own** source of truth. It also **references** three external,
publicly maintained knowledge bases that are updated far too often to copy in. Treat this
file as a **live pointer**, not a snapshot. The numbering below is filing order, not
precedence: source 3 is Splunk's own repository and outranks this library wherever the two
genuinely overlap.

> **Golden rule:** when a source below is relevant, **fetch its live entry-point URL on
> demand** (web fetch / `curl`) and work from that. Do **not** paste large excerpts into
> this library, and do **not** assume any content cached in a prior session is still current.
> Both sources change frequently.

Why pointers instead of copies: both projects publish agent-friendly entry points
(`llms.txt`, `catalog.json`, raw `SKILL.md` files) specifically so an agent can pull the
latest on demand. Copying their content into a local library would silently go stale, and
nothing here would reconcile it.

---

## 1. chambear2809 / splunk-cisco-skills

Production-oriented **agent skills and shell automation** for Splunk Platform, Splunk Cloud,
Splunk Observability Cloud, Cisco integrations, AppDynamics, ThousandEyes, Galileo, external
collectors, and adjacent operational workflows. Render-first and validation-heavy: most
skills expose `--help`, dry-run, render, preflight, then apply, then validate.

- **Canonical repo:** https://github.com/chambear2809/splunk-cisco-skills
- **License:** Apache-2.0 (attribute when reusing; keep the license/notice).

### When to reach for it
- You know a **Cisco product** but not the Splunk app/TA → its `cisco-product-setup` skill.
- You need to **install / configure** a Splunk app, TA, HEC, index, or ACS admin task.
- You need **collector** setup: OTel/OTLP, SC4S (syslog), SC4SNMP, Edge Processor, Stream.
- You need **Enterprise Security**, SOAR, UBA, Federated Analytics, or security routing setup.
- You need **ITSI product install/upgrade** (`splunk-itsi-setup`), or you want ITSI objects
  applied **declaratively from a reviewed spec** rather than hand-rolled REST calls
  (`splunk-itsi-config`: entities, services, embedded KPIs, dependencies, service-template
  links, NEAPs, plus content-pack import from the live Content Library, with lint, GET-only
  preview, drift check, and guarded cleanup). Note the layer boundary and read it before
  assuming coverage: that skill materialises and reconciles a model, it does not decide what
  the model should be, and its own reference material declares an ITSI 4.21 implementation
  baseline while warning that 5.0 features are not validated. Design judgement and 5.0
  behaviour stay with this library's ITSI skills.
- You need **Observability Cloud**, APM, RUM, DBMon, or cloud-integration onboarding.
- You need **AppDynamics**, **ThousandEyes**, or **Galileo MCP** wiring.

### How to use it (fetch live, in this order)
1. **Skill chooser first** — lists every skill, purpose, Splunk 10.5 status, safe first
   command, and validation:
   `https://raw.githubusercontent.com/chambear2809/splunk-cisco-skills/main/SKILL_UX_CATALOG.md`
2. **Repo overview / start-here** (credentials, workflow, deployment matrices):
   `https://raw.githubusercontent.com/chambear2809/splunk-cisco-skills/main/README.md`
3. **A specific skill body** (swap `<skill-name>`):
   `https://raw.githubusercontent.com/chambear2809/splunk-cisco-skills/main/skills/<skill-name>/SKILL.md`
   then its `reference.md` and `scripts/` under the same path when present.
4. Supporting docs when needed: `SKILL_REQUIREMENTS.md`, `DEPLOYMENT_ROLE_MATRIX.md`,
   `CLOUD_DEPLOYMENT_MATRIX.md`, `SPLUNK_10_5_COMPATIBILITY.md` (same raw path prefix).

### Safety carry-overs (honor these when running its scripts)
- Keep all secrets in its local `credentials` file or `--*-file` flags — never in chat or
  command-line args, where they end up in shell history and terminal scrollback.
- Prefer `--help` → dry-run/render/preflight → apply → validate. Review rendered artifacts
  before any mutating phase.

---

## 2. fenre / splunk-monitoring-use-cases

A curated catalog of **7900+ IT infrastructure monitoring use cases** for Splunk across 23
technology domains. Each use case carries criticality, SPL (and a CIM `tstats` variant where
available), CIM data-model mappings, implementation guidance, equipment tagging, and
visualization hints.

- **Agent entry point (start here):** https://fenre.github.io/splunk-monitoring-use-cases/llms.txt
- **Raw fallbacks (if GitHub Pages is blocked):**
  - `https://raw.githubusercontent.com/fenre/splunk-monitoring-use-cases/main/llms-full.txt`
  - `https://raw.githubusercontent.com/fenre/splunk-monitoring-use-cases/main/catalog.json`

### When to reach for it
- You need **ready-made SPL** to monitor a technology (servers, VMware/Hyper-V, containers,
  cloud, network, storage, DB, identity, security, IoT/OT, and more).
- You are **designing ITSI KPIs / base searches** and want a vetted starting query + the CIM
  mapping and criticality for a metric.
- You want to **scope a project** by technology domain, or map stated requirements to
  concrete monitoring use cases.
- You need **detections** or compliance-framework coverage (GDPR, NIS2, DORA, ISO 27001, etc.).

### How to use it (fetch live)
1. `llms.txt` — the index: 23 categories with per-category descriptions and links.
2. `llms-full.txt` — the complete use-case index (ID, title, criticality) for keyword search.
3. `catalog.json` (+ `docs/catalog-schema.md`) — machine-readable catalog for structured
   queries; each use case has a `UC-<x.y.z>` ID for traceability.
4. Per-category `_category.json` under `content/cat-NN-*/` for a full category's sidecars.

### Steering directives (from the source — apply when reusing its SPL)
- Prefer the **CIM `tstats`** variant over raw `search` in high-volume environments.
- Prefer `stats` over `transaction` unless session grouping is strictly required.
- SPL is a **starting point**: adjust index names, thresholds, time ranges, and the assumed
  App/TA to your own environment before use.
- Cite the specific **UC-ID** (e.g. `UC-1.1.1`) when you carry a use case into a deliverable.

---

## 3. splunk / splunk-agent-skills

Splunk's **own** experimental agent skills. Different genre from the two sources above and
from this library: every skill is advisory and read-only by construction, reasoning from
current public documentation plus evidence the user supplies, and explicitly refusing to
change a deployment. Where a task crosses its boundary it routes rather than acts.

- **Canonical repo:** https://github.com/splunk/splunk-agent-skills
- **License:** Apache-2.0. Experimental, and *not* covered by a Splunk support contract —
  its own README says so. Do not present it to a Splunk user as supported product guidance.
- **Precedence:** it is the vendor's repository. On any genuine overlap, prefer it and say
  so; the useful contribution here is then a pointer, not a second opinion.

### When to reach for it
- A **platform-level diagnosis** where the deliverable is a cited, evidence-labelled
  finding rather than a change: slow or queued searches, HEC delivery failures, SAML and
  role/capability access problems, health and diagnostic collection, vulnerability or
  compliance posture.
- **Upgrade or lifecycle planning** for Splunk Enterprise or Cloud, or app/add-on
  packaging, compatibility, and migration questions.
- **Knowledge-object hygiene**: ownership, orphans, ACLs, naming collisions, lookups,
  search-head-cluster comparison.
- **Deployment server / forwarder fleet** mechanics — server classes, client filters,
  phone-home, effective assignment, Remote Upgrader boundaries.
- **Dashboard conversion** from classic Simple XML to Dashboard Studio, or building a
  custom visualization.
- A **general product question** needing citations and an explicit statement of what is
  uncertain.

### How to use it (fetch live)
1. Skill list and install commands: `https://raw.githubusercontent.com/splunk/splunk-agent-skills/main/README.md`
2. A specific skill body: `https://raw.githubusercontent.com/splunk/splunk-agent-skills/main/skills/<skill-name>/SKILL.md`
3. Support and security posture before quoting it to anyone: `SUPPORT.md`, `SECURITY.md`.

### Volatility warning
This repository churns hard, and not only additively — it has both trimmed its published
set to a single domain and repopulated it within the same month. Never hard-code its skill
list, its skill count, or a claim about what it does not cover; re-check at use time. Two of
its skills also need a separately installed CLI (`acs`, and a Go-built `splsearch`), so a
skill being listed does not mean it is runnable here.

## Attribution & hygiene
- These are **third-party** sources. Attribute them, respect their licenses (chambear2809 and
  splunk are both Apache-2.0), and do not present their content as the team's own authored
  material.
- If either URL 404s or a project restructures, update the entry-point URLs in **this file**
  (it is the single place the library records them).
- Do not fetch these on every session by default — only when the active task matches the
  "when to reach for it" triggers above.
