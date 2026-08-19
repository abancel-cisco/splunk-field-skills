---
name: splunk-itsi-hybrid-action-dispatching
category: itsi
description: Configure and troubleshoot Splunk ITSI hybrid action dispatching, where a manager node (typically a Splunk Cloud search head) queues notable-event action tasks in the `itsi_notable_event_actions_queue` KV store collection and an executor node (typically an on-premises heavy forwarder) consumes and runs them locally. Covers the execution mechanics and queue lifecycle, executor enablement, proxy configuration for egress-restricted environments, and the `earemotesearch` errors and queue backlogs that surface when the consumer cannot reach the manager node. Use when notable-event actions are queued but never execute, when actions must run on-premises against targets a cloud search head cannot reach, or when troubleshooting `earemotesearch` / ProxyError failures in the action queue.
disable-model-invocation: true
---
# Splunk ITSI Hybrid Action Dispatching

**Validated on:** ITSI 4.21.x. Not re-verified on ITSI 5.0.

## Architecture
In a hybrid action dispatching configuration:
*   **Manager Node** (typically Splunk Cloud Search Head): Queues notable event action tasks in the `itsi_notable_event_actions_queue` KV store collection.
*   **Executor Node** (typically an on-premises Heavy Forwarder): Runs the queue consumer to execute queued tasks locally.

## Execution Mechanics
When executing notable event actions (e.g., a webhook), the Executor executes a search command containing the `earemotesearch` command:
```spl
| stats count | ... | appendcols [earemotesearch remote_spl="| stats count | ... | `itsi_notable_group_lookup`"] | sendalert "itsi_event_action_webhook" ...
```
This requires outbound HTTP traffic over port **8089** from the Executor node back to the Manager node's management port (REST API) to retrieve notable event details.

## Troubleshooting Proxy/Tunnel Errors
If the Executor node is configured to use an outbound HTTP/HTTPS proxy, `earemotesearch` may fail with:
> `Caused by ProxyError('Cannot connect to proxy.', OSError('Tunnel connection failed: 403 Forbidden'))`

### Diagnosis
1.  Verify direct connectivity from the Executor to the Manager's port 8089 (e.g., `nc -zv <manager-host> 8089`).
2.  If direct connection succeeds but Splunk fails with `ProxyError: 403 Forbidden`, the proxy server itself is rejecting the `CONNECT` request to establish a tunnel over port 8089.

### Action Plan
Configure proxy bypass on the Executor node's `server.conf` (located in `$SPLUNK_HOME/etc/system/local/server.conf`) under the `[proxyConfig]` stanza:

```ini
[proxyConfig]
no_proxy = localhost, 127.0.0.1, <manager-host-or-domain>
```

For example:
```ini
[proxyConfig]
no_proxy = localhost, 127.0.0.1, buttercup-itsi.splunkcloud.com
```

Alternatively, if the Executor node does not need a proxy for external communication, disable proxy routing entirely in `server.conf`. Restart the Splunk instance on the Executor node to apply changes.
