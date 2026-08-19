---
name: otel-vs-splunk-ingestion
category: observability
description: Decision framework for picking the right data collection method in a Splunk ITSI / Observability Cloud project. Compares OTel Collector (Splunk Distribution) native receivers vs Splunk Universal Forwarder vs Splunk DB Connect vs commercial JMS / third-party add-ons. Strong default toward OTel native receivers (oracledbreceiver, sqlserverreceiver, jmxreceiver, filelog, hostmetrics, tibcoems) on dev instances; covers when UF or DB Connect is justified. Use when designing data ingestion for a Splunk project, populating the `Collection Method/Agent` column in a KPI tracker, deciding between OTel and UF / DB Connect for a given source, when the user mentions OTel collector / SIM / hostmetrics / jmxreceiver / DB Connect / HEC / JMS modular input / deployment server / OpAmp / TA sourcetype compatibility, or when the customer's prod ingestion uses a commercial add-on you cannot replicate on a dev tenant.
disable-model-invocation: true
---

# OTel vs Splunk Ingestion — Decision Framework

How to pick the right data collection mechanism for a Splunk project. Default-toward-OTel decision tree, with explicit carve-outs for when UF / DB Connect / commercial add-ons remain justified.

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## When to use this skill

- Designing data ingestion for a Splunk ITSI or Observability Cloud project
- Populating the `Collection Method/Agent` column in a KPI or Data Sources tracker
- Asked "should I use UF or OTel for this?"
- The customer's production uses a commercial add-on (e.g. JMS Modular Input) and you need to demonstrate parity on a dev instance without licensing it
- Designing a Per-Host Ingestion plan
- Picking between OTel native receivers vs Splunk DB Connect for database telemetry

## The default rule

> **On a dev instance, prefer the OTel Collector (Splunk Distribution) with native receivers.**
> Reach for UF / DB Connect / commercial add-ons only when OTel can't do the job or the customer's prod will use them and parity matters.

Three reasons OTel is the default in 2026:

1. **Single agent, multiple receivers.** One installed binary handles host metrics, JMX, file logs, OS perfcounters, DB queries, JMS, traces. Fewer things to provision / open ports for / monitor.
2. **Splunk Cloud forward roadmap.** Splunk has clearly bet on OTel as the modern ingestion path for both Splunk Enterprise / Cloud (logs/metrics) and Splunk Observability Cloud (traces/RUM/metrics). UF and DB Connect are maintenance-mode.
3. **Config as code.** A collector's configuration is a YAML file: versioned, reviewable, idempotent, and reproducible from your repository rather than from the state of a server's app tree. Be honest about the trade-off, though — that file still has to be *delivered*, and OTel has no Splunk-side equivalent of the deployment server. This is the one dimension where UF is ahead, not behind (see "When UF is still justified").

## Decision tree per data source type

```
Data source = host CPU / memory / disk / network
  -> OTel hostmetrics receiver. Always.

Data source = Windows perf counters / event logs
  -> OTel windowsperfcountersreceiver + windowseventlogreceiver. Always.

Data source = JVM / JBoss / Tomcat / application-server JMX
  -> OTel jmxreceiver. Localhost no-auth is fine if collector is on same host.
     Fallback: jmx_exporter -> OTel prometheusreceiver if jmxreceiver doesn't
     fit your beans.

Data source = file log (text logs, JSON logs, structured app logs)
  -> OTel filelog receiver. Configure multiline / encoding / time format as needed.
     Fallback: UF only if filelog can't handle the format (extremely rare in 2026),
              if a TA has to consume the data under its own sourcetype, or if the
              customer's ops team standardizes on UF.

Data source = message-broker queue depths / message rates
  -> The OTel receiver for your broker (tibcoems, kafkametrics, rabbitmq,
     activemq...). Expect to need a read-only admin account and, often, an
     explicit list of the queues to watch.
     Caveat: several broker receivers live in otel-collector-contrib rather
     than the Splunk Distribution core. They work, but they are not flagged
     GA-stable, and some risk policies refuse a contrib-only component on a
     path to production. See "When DB Connect is still justified" below.

Data source = Oracle DB metrics / health
  -> OTel oracledbreceiver. Needs read-only DB user.
     Fallback to Splunk DB Connect ONLY if:
       a) customer already runs DB Connect in prod and ops parity matters, OR
       b) you need a custom SQL query oracledbreceiver doesn't ship a metric for
          -> use OTel sqlqueryreceiver before falling back to DB Connect.

Data source = SQL Server metrics / health
  -> OTel sqlserverreceiver (Windows perfcounters + DMV queries).
     Same fallback rules as Oracle.

Data source = MySQL / PostgreSQL / MongoDB
  -> OTel mysqlreceiver / postgresqlreceiver / mongodbreceiver. Native.

Data source = HTTP / TCP synthetic check
  -> OTel httpcheckreceiver / tcpcheckreceiver. Lightweight.

Data source = SAP application data (ECC, PI/PO, S/4)
  -> PowerConnect for SAP. Not negotiable; OTel doesn't have an SAP ABAP-aware
     collector. PowerConnect runs ABAP-side and pushes via HEC.

Data source = generic JMS - ActiveMQ, IBM MQ, other JMS providers
  -> OTel kafkareceiver if Kafka. For ActiveMQ/IBM MQ:
     a) check OTel contrib for a native receiver,
     b) if customer uses Splunk Connect for Kafka in prod, use it for parity,
     c) commercial JMS Modular Input only as last resort (paid add-on,
        production-tested, may be required for parity).

Data source = SAP HANA / Azure SQL / cloud-managed DB
  -> Check OTel receiver coverage first; cloud-managed often has native exporters.

Data source = SNMP / network device metrics
  -> Splunk Connect for SNMP (OTel-based) or vendor-specific add-ons (Cisco etc.).

Data source = Container metrics (k8s, ECS, etc.)
  -> OTel kubeletstats + k8s_cluster + k8s_events. Default.
```

## Common collector + receiver mappings

A reference table for the `Collection Method/Agent` column in a Splunk project tracker:

| Source | `Collection Method/Agent` value | Index target | Sourcetype convention |
|---|---|---|---|
| Host CPU/Mem/Disk/Net | `OTel hostmetrics` | `sim_metrics` | `host_metrics (OTel)` |
| Windows perfcounters | `OTel windowsperfcounters` | `sim_metrics` | `winperf (OTel)` |
| Windows event log | `OTel windowseventlog` | `windows` | `WinEventLog` |
| JBoss / Tomcat / application-server JMX | `OTel jmxreceiver` | `sim_metrics` | `jmx (OTel)` |
| Message-broker queues (default) | `OTel receiver for the broker (tibcoems, kafkametrics, rabbitmq...)` | `sim_metrics` or `<perimeter>` | `<vendor>:<component>` |
| Message-broker queues (no usable receiver) | `Splunk DB Connect on a heavy forwarder (JDBC to the broker's admin interface)` | `<perimeter>` (event-based) → derived metrics | `<vendor>:<component>_stats` |
| App log files (Linux/Windows) | `OTel filelog receiver` | `<perimeter>` (e.g. `middleware`, `fulfilment`) | `<vendor>:<component>` (e.g. `jboss:server`, `broker:queue`) |
| Oracle metrics | `OTel oracledbreceiver` (native) | `<perimeter>_db` | `oracle (OTel native)` |
| SQL Server metrics | `OTel sqlserverreceiver` (native) | `<perimeter>_db` | `mssql (OTel native)` |
| Custom DB query | `OTel sqlqueryreceiver` | `<perimeter>_db` | `oracle:custom` or similar |
| HTTP synthetic | `OTel httpcheckreceiver` | `sim_metrics` | `http_check` |
| SAP application | `PowerConnect for SAP` | `sap` or `sap_pc` | `sap_pc:*` |
| OS process listing / process_iterator | `OTel hostmetrics (process scraper)` | `sim_metrics` | `host_metrics (OTel)` |

The `sim_metrics` index is the default created by the SIM (Splunk Infrastructure Monitoring) add-on for ITSI. **Not** `em_metrics` — that was a legacy name; if you see it in docs or a tracker, replace with `sim_metrics`.

## When UF is still justified

Don't use UF reflexively. But it's the right call when:

1. **Customer ops team already runs UF at scale** and won't accept introducing a second agent for this project. Pick your battles.
2. **Configuration has to be managed from Splunk itself.** A deployment server plus `serverclass.conf` pushes inputs and apps to thousands of forwarders, and withdraws them again, from inside the platform the team already administers. OTel has no equivalent yet: OpAmp is the right direction and worth tracking, but until it is there you are managing collector config with Ansible / Puppet / Chef or a Kubernetes operator. That is a second toolchain for the same fleet, and often a second team — which is a real objection from an ops group, not a preference.
3. **An add-on has to work end to end.** A TA's props, transforms, eventtypes and CIM mappings are all keyed on sourcetype, and so is any ITSI or ES content sitting on top of them. Change how the data arrives and none of it fires. You can make OTel emit the sourcetype and the shape a TA expects, but then you have reimplemented the add-on's contract and you own it at every future TA release. UF plus the TA gives you the whole chain, search-time logic included — which for a deep TA like Splunk_TA_nix is most of its value, ingestion being the smaller part.
4. **You need scripted inputs that aren't easily wrapped by OTel filelog** (e.g. running a CLI command and ingesting its stdout). Possible in OTel via `execreceiver`, but UF's `[script://]` input is older and more battle-tested.
5. **Bandwidth-constrained edge sites** where UF's tested compression / deduplication is more optimized than OTel's current state.

When you do use UF, document the reason in the Data Sources tab: `UF (justification: <reason>)` rather than just `UF`.

## When DB Connect is still justified

Almost never as your first choice in 2026, but legitimate when:

1. **Customer's prod uses DB Connect** and your dev instance must demonstrate operational parity.
2. **You need a database type the OTel ecosystem doesn't have a receiver for** (rare; check `otel-collector-contrib` repo first).
3. **The KPI needs a transactional query** that fits the DB Connect "input scheduler with checkpoints" model better than OTel sqlqueryreceiver's polling.
4. **The OTel receiver exists only as `otel-collector-contrib` and the customer's risk policy refuses contrib-only components** (i.e. they want an enterprise-supported path). DB Connect is a Splunk-supported add-on; OTel contrib receivers are community-maintained.

When you do use DB Connect: document the trade-off (extra JVM agent on the SH or HF, separate add-on lifecycle, separate credential storage, no native metric typing — you build metrics from query results).

Reason 4 turns up most often with message brokers, several of which expose their admin
statistics through a SQL-like interface that a JDBC driver can query. Two things are
worth knowing before you commit to it. Put DB Connect on a heavy forwarder rather than
the search head, so the polling and its JVM stay off the box serving user searches. And
budget for a conversion step: a scheduled input yields one event per object per poll, so
a summary index or metric-store job has to turn those rows into the time series a KPI
reads — which is the work the OTel receiver would have done for you. Record it in the
tracker as an exception to the OTel default, with the reason, so the next person doesn't
read it as a preference.

## When commercial / third-party JMS add-ons are justified

This is a specific gotcha. Pattern: customer's production uses a paid Splunk add-on (a JMS or broker input from Splunkbase, say). They show you a dashboard built from that data. Your dev instance does not have the license. The question becomes: *can we replicate the result with OTel + free tools?*

Approach:
1. **Don't replicate the exact ingestion**. The customer's prod ingestion is theirs; you don't need to mirror it.
2. **Decompose the dashboard into the KPIs it shows.** Usually it's a few KPI families: queue depth, message rate, error rate, throughput per topic.
3. **Map each KPI family to an OTel-native equivalent**:
   - Queue depth -> the OTel receiver for your broker (tibcoems, kafkametrics, rabbitmq...)
   - Message rate -> same receivers
   - Error rate -> OTel filelog on the broker's error log + extraction
4. **Build the equivalent dashboard on the dev instance** from those KPIs.
5. **Document the gap explicitly** in the tracker: "Customer's prod uses <paid add-on>. The dev instance demonstrates equivalent KPIs via <OTel receiver> + filelog. Licensing decision for prod = customer's commercial track."

This is honest (you're not pretending to be the commercial tool), demonstrates value (you can do most of what they need without paying the commercial tag), and respects the boundary (don't propose to rip out a working prod tool).

## Sample data first

Before committing to any collector for a KPI, **insist on a data sample**. Specifically:

- For log-based KPIs: 1+ MB of raw log lines covering at least one error condition and one normal operation
- For metric-based KPIs: confirmation of the metric exists in the receiver's output (run the receiver against a test endpoint, look at the published metrics)
- For DB-based KPIs: a sample query result (CSV or screenshot) showing the columns and value ranges

Without a sample the means to implement is unconfirmed, so treat the KPI as provisional and do not count it as committed scope until a sample exists.

## OTel collector packaging in a Splunk project

Use the **Splunk Distribution of OpenTelemetry Collector** rather than upstream OpenTelemetry. Reasons:

1. **A curated receiver set with Splunk-tested defaults**, so you are not assembling and vetting a collector build yourself.
2. **HEC exporter pre-wired** for sending to Splunk Cloud.
3. **SignalFx exporter pre-wired** for Observability Cloud.
4. **Splunk support boundary** when something breaks in prod.

Installation defaults:
- Linux: `/etc/otel/collector/agent_config.yaml`
- Windows: `C:\ProgramData\Splunk\OpenTelemetry Collector\agent_config.yaml`
- Default ports: 4317 (OTLP gRPC), 4318 (OTLP HTTP), 13133 (health), 8888 (metrics)

## Splunk Infrastructure Monitoring (SIM) add-on

The SIM add-on for ITSI is what bridges Splunk Observability Cloud metrics into Splunk ITSI Glass Tables / Service Analyzer. Important conventions:

- Default index it creates: `sim_metrics` (NOT `em_metrics` — that was a pre-rename legacy)
- It expects metrics with `host.name` dimension for the entity lookup to ITSI
- It expects the SignalFx API token (the long opaque token from the O11y org); supply it from the environment or a secret store, never inline in a committed config

When populating the `Index` column of a Data Sources / KPIs row for a metric flowing via SIM, write `sim_metrics`. Use the perimeter-specific index (e.g. `middleware`, `fulfilment`, `erp`) only for log data.

## Per-host ingestion checklist

For each host in the project, define rows in the Per-Host Ingestion tab covering all of these (where applicable):

- [ ] Hostmetrics (always)
- [ ] One filelog row per distinct app log on the host
- [ ] JMX row(s) for any JVM app on the host
- [ ] Windows-specific: windowseventlog + windowsperfcounters
- [ ] DB metrics row if the host is a DB host
- [ ] Synthetic HTTP check if the host exposes an HTTP endpoint that matters
- [ ] Trace receiver only if APM-instrumented (typically separate decision)

Give each row its own Status, owner, and `Feeds KPI(s)` reference, so every ingestion decision traces to the KPI that depends on it.

## Anti-patterns

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| Defaulting to UF "because we always use UF" | Two-agent footprint, more ops work, lagging on modern features | OTel as default; UF only with documented justification |
| Splunk DB Connect for new builds | Extra JVM agent, separate add-on lifecycle, slower iteration | OTel db receivers; DB Connect only for prod parity |
| Mixing collection methods within one tab without saying why | Reviewer can't tell what's a deliberate choice vs an accident | Document collector choice + reason in Notes column |
| Trying to replicate a commercial add-on's exact ingestion on a dev instance | Wastes time, can't do it without license | Decompose to KPIs, build equivalent via OTel, document the boundary |
| Using `em_metrics` as the SIM index | Outdated; SIM uses `sim_metrics` by default | `sim_metrics` everywhere |
| Multiple OTel collectors on one host (one per perimeter) | Adds packaging burden, port conflicts | One collector per host with multiple receiver configs |
| One sourcetype for everything a multi-component product emits | Loses the ability to apply per-component extractions | Per-component sourcetype (`<vendor>:<component>`, e.g. `broker:server`, `broker:queue`, `broker:admin`) |

## Documenting the decision in the tracker

In the Data Sources tab, the `Collection Method` column should be precise enough that an SE who's never seen the customer can replicate the design:

Good:
- `OTel filelog receiver (multiline regex: ^\d{4}-\d{2}-\d{2}; encoding: utf-8)`
- `OTel oracledbreceiver (read-only role: splunk_ro; port 1541)`
- `OTel <broker> receiver (admin URL tcp://<host>:<port>; svc acct: <read-only account>)`
- `PowerConnect for SAP (ABAP install on the ECC system, push via HEC)`

Bad (vague):
- `otel`
- `JMX`
- `Splunk add-on`

## Related skills

- `splunk-itsi-entity-cmdb-lookup` — the CMDB lookup that enriches the entities this telemetry lands on
- `splunk-itsi-kpi-creation-via-api` — turning the collected data into KPIs
- `splunk-itsi-service-tree-design` — where those KPIs hang in the service tree
- `splunk-itsi-content-pack-creation` — packaging the base searches that consume these sources

Treat SignalFx and HEC tokens as credentials throughout. Keep them in the collector's
environment or a secret store, never in a tracker, a config committed to a repository, or
a document shared with the customer.
