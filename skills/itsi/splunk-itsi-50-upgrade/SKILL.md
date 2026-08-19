---
name: splunk-itsi-50-upgrade
category: itsi
description: Upgrade Splunk IT Service Intelligence to 5.0 on a single-instance or distributed on-prem lab — prerequisites, Splunk Enterprise co-upgrade, backup before upgrade, ITSI package extraction (not splunk install app), SA-IndexCreation on indexers, post-upgrade validation, and rollback. Covers direct upgrade from 4.21.x (within three-version rule), compatibility matrix checks, Python 3 ordering no longer applies on Splunk 10.x, and version-specific post-install tasks. Use when upgrading a lab or production stack to ITSI 5.0, planning maintenance windows for Splunk+ITSI co-upgrade, creating pre-upgrade backups, or rolling back a failed ITSI upgrade.
disable-model-invocation: true
---

# ITSI 5.0 — Upgrade Runbook

On-prem upgrade procedure for **ITSI 5.0**. Splunk Cloud upgrades are coordinated with Splunk Support.

**Prerequisites doc:** [Before you upgrade ITSI](https://help.splunk.com/en/splunk-it-service-intelligence/splunk-it-service-intelligence/install-and-upgrade/4.20/upgrading/before-you-upgrade-it-service-intelligence)

**Single-instance procedure:** [Upgrade ITSI on a single instance](https://help.splunk.com/en/splunk-it-service-intelligence/splunk-it-service-intelligence/install-and-upgrade/4.20/upgrading/upgrade-it-service-intelligence-on-a-single-instance)

## Upgrade path rules

- ITSI supports upgrades from **up to three versions prior**. 4.21.x → 5.0 is a **direct** upgrade (one major jump).
- If source ITSI is **older than three versions** behind target, step through intermediate versions first.
- Upgrade **Splunk Enterprise and ITSI in the same maintenance window** when both need updating.
- **Python 3 ordering** (upgrade ITSI before Splunk on 8.x) does **not** apply when already on Splunk 10.x.

## Pre-flight checklist

```
Task Progress:
- [ ] Record current versions (splunk version, SA-ITOA version, SHC/cluster topology)
- [ ] Review 5.0 known issues and removed features
- [ ] Verify Splunk Enterprise ↔ ITSI 5.0 compatibility matrix
- [ ] Verify Java on search heads (8–11 or 17; OpenJDK or Oracle)
- [ ] Full backup of $SPLUNK_HOME (or at minimum etc/apps + etc/users + KV store)
- [ ] Export ITSI partial backup via UI if team-scoped objects matter
- [ ] Stop Splunk cleanly
- [ ] Disk space check (ITSI package + migration headroom)
- [ ] Notify: searches/KPIs unavailable during upgrade
```

### Version discovery commands

```bash
$SPLUNK_HOME/bin/splunk version
grep '^version' $SPLUNK_HOME/etc/apps/SA-ITOA/default/app.conf
```

## Backup strategy (lab)

Prefer **two layers**:

1. **Filesystem backup** — tarball of `$SPLUNK_HOME` or selective `etc/apps`, `etc/users`, `etc/system/local`, `var/lib/splunk/kvstore`.
2. **ITSI partial backup** — UI: Configuration → Backup/Restore → partial backup (5.0 auto-includes team dependencies).

Example filesystem backup:

```bash
# Stop Splunk first
$SPLUNK_HOME/bin/splunk stop

BACKUP_DIR=/path/to/backups/itsi50-pre-upgrade-$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/splunk-etc-apps.tgz" -C $SPLUNK_HOME etc/apps
tar -czf "$BACKUP_DIR/splunk-etc-users.tgz" -C $SPLUNK_HOME etc/users
tar -czf "$BACKUP_DIR/splunk-etc-system-local.tgz" -C $SPLUNK_HOME etc/system/local
# KV store (ITSI entities, NEAPs, teams)
tar -czf "$BACKUP_DIR/splunk-kvstore.tgz" -C $SPLUNK_HOME var/lib/splunk/kvstore
```

**Rollback:** restore tarballs to `$SPLUNK_HOME`, reinstall prior ITSI `.spl` if apps were overwritten, start Splunk.

## Splunk Enterprise co-upgrade (when needed)

If the target Splunk version is newer than what's installed:

1. Stop Splunk.
2. Back up `$SPLUNK_HOME`.
3. Extract new Splunk tarball **over** existing install (preserve `etc/` and `var/`).
4. Run `$SPLUNK_HOME/bin/splunk migrate <old-version>` if prompted.
5. Start Splunk; verify `splunk version`.

**Lab binaries (Linux amd64):** see project skill `lab-environment` for paths. Latest in archive: `splunk-10.4.1-5a009d941268-linux-amd64.tgz`.

## ITSI 5.0 install

**Critical:** ITSI must be installed by **extracting the package into `etc/apps`**. Do **not** use Splunk Web app manager or `splunk install app` for ITSI.

```bash
$SPLUNK_HOME/bin/splunk stop

# Extract ITSI 5.0 package
cd /tmp
tar -xzf splunk-it-service-intelligence_500.spl   # or unzip if .spl is zip format
# Inspect top-level folder name (typically splunk-it-service-intelligence or SA-ITOA bundle)

# Copy/replace into etc/apps — follow package README for exact folder names
# Standard: entire ITSI app bundle extracts multiple apps (SA-ITOA, itsi, etc.)
cp -R splunk-it-service-intelligence/* $SPLUNK_HOME/etc/apps/

# Fix ownership if needed
chown -R splunk:splunk $SPLUNK_HOME/etc/apps/
```

Start Splunk; first start runs **ITSI migration** — can take several minutes.

```bash
$SPLUNK_HOME/bin/splunk start
tail -f $SPLUNK_HOME/var/log/splunk/splunkd.log
```

## Indexers and SA-IndexCreation

On distributed deployments, place **SA-IndexCreation** on all indexers (and heavy forwarders). For indexer clusters, use the configuration bundle method from the cluster manager.

Single-instance: SA-IndexCreation is already local.

## Post-upgrade validation

```
- [ ] splunk version shows expected Enterprise build
- [ ] SA-ITOA version = 5.0.x in app.conf
- [ ] ITSI app loads in Splunk Web (no 500 errors)
- [ ] Service Analyzer opens; at least one service shows health
- [ ] Episode Review loads
- [ ] REST smoke test: GET /servicesNS/nobody/SA-ITOA/itoa_interface/service?count=1
- [ ] Check splunkd.log and itsi_migration.log for errors
- [ ] Re-apply licenses if needed (Enterprise + ITSI NFR)
- [ ] Review version-specific upgrade notes for post-install tasks
- [ ] Re-test custom content packs and overlay apps (SIM OS hosts fix, etc.)
```

### REST smoke test

```bash
curl -sS -k -u admin:'$PASSWORD' \
  "$SPLUNK_URL:8089/servicesNS/nobody/SA-ITOA/itoa_interface/service?output_mode=json&count=1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('services:', len(d.get('entry',[])))"
```

## Companion apps to verify

After ITSI upgrade, check compatibility and upgrade if needed:

| App | Why |
|-----|-----|
| Splunk App for Content Packs | Content Library UI (5.0) |
| Splunk ML / AI Toolkit | Event iQ, threshold recommendations |
| Python for Scientific Computing | ML Toolkit dependency |
| Custom overlay CPs | May need rebuild for 5.0 API changes |

See `splunk-itsi-common-errors` for AI Toolkit / Scientific Python version pinning if threshold AI breaks.

## Rollback procedure

1. Stop Splunk.
2. Restore pre-upgrade `etc/apps` tarball (or remove ITSI 5.0 apps and restore 4.21.x `.spl` extract).
3. Restore `var/lib/splunk/kvstore` if migration corrupted state.
4. If Splunk Enterprise was upgraded, restore prior Splunk binaries or re-extract prior `.tgz`.
5. Start Splunk; verify SA-ITOA version reverted.
6. Re-import ITSI partial backup if filesystem restore insufficient.

## SHC note

Search head cluster upgrades are multi-step (deployer bundle, rolling restart). This lab runbook targets **single-instance** first; adapt using Splunk's SHC ITSI upgrade doc if the remote host is clustered.
