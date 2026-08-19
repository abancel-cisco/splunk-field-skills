# Contributing

Pull requests are welcome, particularly corrections and version re-validations.

## The three rules that matter

**1. No customer-identifying information.** Ever, anywhere, including in examples,
sample output, screenshots, URLs, and commit messages. Git history is permanent, and a
customer name scrubbed in a later commit is still public. Use `Buttercup` as the
placeholder organisation, `buttercup-itsi.splunkcloud.com` style hostnames, and the
[RFC 5737](https://datatracker.ietf.org/doc/html/rfc5737) documentation ranges
(`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`) for IP addresses. Never a real
stack hostname, a real username, or a real email address.

The same applies to internal-only material: lab hostnames, internal enablement content,
and anything not intended for a public audience.

**2. Say what you validated against.** Every skill states the product versions and the
date behind it, for example *"Validated on ITSI 5.0.1 / Splunk Enterprise 10.4.1,
2026-08-19."* A skill without a version note cannot be trusted by anyone else, because
they have no way to judge whether it still applies. "It works on my stack" is not a
version note.

**3. Check it isn't already covered elsewhere.** This repository is small on purpose. A
skill that duplicates one in a larger, better-maintained catalogue is worse than no skill
at all, because an agent may load ours instead of theirs and act on the staler of the two.

Before writing a new skill, search these first:

| Catalogue | Covers | Check before writing about |
|---|---|---|
| [`splunk/splunk-agent-skills`](https://github.com/splunk/splunk-agent-skills) | Splunk's own experimental skills | anything — this is the vendor's repository and takes precedence over ours on any overlap |
| [`chambear2809/splunk-cisco-skills`](https://github.com/chambear2809/splunk-cisco-skills) | ~175 skills: Splunk and Cloud administration, TA and app install, Cisco onboarding, AppDynamics, ThousandEyes, collectors, SC4S, HEC, ACS | product install, configuration, and platform automation |
| [`fenre/splunk-monitoring-use-cases`](https://fenre.github.io/splunk-monitoring-use-cases/) | ready-made SPL, CIM-aligned detections, KPI base searches by technology domain | any skill whose real payload is a search rather than a procedure |

```bash
npx skills add splunk/splunk-agent-skills --list
npx skills add chambear2809/splunk-cisco-skills --list
```

If a skill already exists there, the useful contribution is usually a link, not a copy.
[`skills/_meta/external-knowledge-sources`](skills/_meta/external-knowledge-sources/SKILL.md)
exists so agents can be pointed at those catalogues live, and it is a better home for a
pointer than a duplicated skill that will drift.

Overlap is not automatically disqualifying — adjacent is fine, duplicated is not. As an
example, `splunk-dashboard-studio-rest` (create Studio dashboards through the REST API)
sits next to Splunk's own `splunk-dashboard-converter` (convert classic Simple XML to
Studio) without colliding: same product surface, different task. If your skill overlaps,
say so in the PR and explain what it does that the existing one does not.

The same test applies inside this repository. Prefer extending an existing skill over
adding a near-neighbour, and if you find two skills that have grown into each other,
merging them is a welcome pull request.

## Skill format

Skills follow the [Agent Skills specification](https://agentskills.io/specification) and
live at `skills/<category>/<skill-name>/SKILL.md`. Categories in use are `itsi`,
`platform`, `observability`, and `_meta`; propose a new one in your PR if your skill
doesn't fit.

Required frontmatter:

```yaml
---
name: splunk-itsi-example-thing        # must equal the directory name
category: itsi
description: >
  What the skill does, and when an agent should reach for it. This is the only
  thing an agent sees when deciding whether to load the skill, so it needs to
  carry both the capability and the trigger conditions.
disable-model-invocation: true          # optional; set for specialist skills
---
```

`name` must match the directory name exactly — the installer resolves `--skill <name>`
against the directory, so a mismatch makes the skill uninstallable.

Set `disable-model-invocation: true` for narrow, specialist skills that should only load
when explicitly asked for. Leave it off for skills that should fire from ambient context.

## Writing guidance

Skills are read by agents, not people, but they are debugged by people.

- Lead with the failure mode. Most of the value here is in "this looks like it should
  work and doesn't, here's why".
- Give the payload, not a description of the payload. Real JSON, real SPL, real
  `curl`.
- State the order of operations where order matters — most ITSI REST work is
  order-dependent, and that ordering is the part that isn't documented.
- Mark anything destructive clearly, and say what to back up first.
- Prefer a worked example over an abstract template.

## Before you open a PR

```bash
python3 tools/validate_skills.py
```

This checks frontmatter, name/directory agreement, category validity, and scans for
identifiers that look like real customer data. CI runs the same check plus
[gitleaks](https://github.com/gitleaks/gitleaks).

If you add or move a skill, also update:

- the skill index table in [`README.md`](README.md)
- [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), which lists skill paths so
  nested categories appear in the default `npx skills add` menu

Both are checked by the validator.

## Licence

Contributions are accepted under the [Apache License 2.0](LICENSE).
