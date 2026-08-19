---
name: external-knowledge-sources
category: _meta
description: >-
  Registry of external, actively-maintained knowledge sources this library references LIVE (by pointer, never copied): (1) chambear2809/splunk-cisco-skills — operational setup & automation SKILL.md files for Splunk and Cisco products (install/config workflows, Splunk Cloud ACS, HEC, OTel/SC4S/SC4SNMP collectors, Enterprise Security, ITSI setup/config, Observability Cloud, AppDynamics, ThousandEyes, Galileo MCP); (2) fenre splunk-monitoring-use-cases — a catalog of 7900+ infrastructure monitoring use cases (SPL + CIM data-model mappings, criticality, TA/app hints) across 23 technology domains. Use when a task needs Splunk/Cisco product setup automation, or ready-made monitoring / KPI / detection SPL, beyond what the local library covers (e.g. "how do I install and configure the Cisco ACI app", "give me SPL to monitor VMware host contention", "what use cases exist for Kubernetes OOM kills"). ALWAYS fetch the live URLs on demand at use time; never rely on a cached snapshot, because both sources are updated frequently.
disable-model-invocation: true
---

# External Knowledge Sources

This library is the team's **own** source of truth. It also **references** two external,
publicly maintained knowledge bases that are updated far too often to copy in. Treat this
file as a **live pointer**, not a snapshot:

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
- You need **ITSI product install/upgrade** or ITSI service/KPI/entity/content-pack *setup*
  automation (complements this library's ITSI *design* skills).
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
- You want to **scope a project** by technology domain, or map customer requirements to
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
  App/TA to the customer's environment before use.
- Cite the specific **UC-ID** (e.g. `UC-1.1.1`) when you carry a use case into a deliverable.

---

## Attribution & hygiene
- These are **third-party** sources. Attribute them, respect their licenses (chambear2809 is
  Apache-2.0), and do not present their content as the team's own authored material.
- If either URL 404s or a project restructures, update the entry-point URLs in **this file**
  (it is the single place the library records them).
- Do not fetch these on every session by default — only when the active task matches the
  "when to reach for it" triggers above.
