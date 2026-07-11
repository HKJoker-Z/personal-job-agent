# Client Proxy and Mihomo TUN Troubleshooting

## Symptom Pattern

On a Linux production host, Docker may listen on `0.0.0.0:8080` and local requests may return HTTP 200 while a remote browser or `curl --noproxy` request stalls. When Mihomo TUN is enabled, its policy rules can capture the Docker Frontend's SYN-ACK return traffic. This is a server return-routing problem, not proof that the client proxy is broken.

Confirm all of the following before changing routing:

```bash
docker compose ps
curl --fail http://127.0.0.1:8080/
curl --fail http://127.0.0.1:8080/api/health
ss -ltn 'sport = :8080'
ip -4 rule show
ip -4 route show table main
```

Use a short, explicitly filtered `tcpdump` capture on the external interface while requesting only `/api/health`. A failed return path commonly shows an inbound SYN without the complete SYN → SYN-ACK → ACK → GET → HTTP response sequence. Captures can contain client addresses and HTTP headers; do not commit them, and delete them after the investigation.

## Production Fix

The Compose application network owns the stable bridge `pja-br0`. Docker's generated `br-<network-id>` name is not suitable for persistent rules because it changes when the network is rebuilt.

The supported IPv4 rule is:

```bash
ip -4 rule add pref 8999 \
  iif pja-br0 \
  ipproto tcp sport 8080 \
  lookup main
```

This rule bypasses Mihomo TUN only for Frontend responses whose TCP source port is 8080. Frontend unrelated egress and Backend HTTPS egress are not matched. Backend port 8000 remains private on the Compose network.

Use `scripts/configure-production-routing.sh` and `deploy/systemd/personal-job-agent-routing.service` for persistent installation. The script refuses to overwrite a different pref 8999 rule and removes only the fully matching project rule. During migration, pref 8998 may be used temporarily for the same `pja-br0` selector; do not remove the last verified working rule until its replacement has passed remote-client testing.

## Why `exclude-interface` Is Not the Default

Mihomo supports `tun.exclude-interface`, but excluding `pja-br0` bypasses TUN for the entire bridge. That is broader than the published-port return-path fix and may break Backend access to external APIs. Use it only after proving every required Frontend and Backend external request works without Mihomo, confirming there is no conflicting `include-interface`, and explicitly accepting the broader bypass. Do not configure it together with the project's precise policy rule.

## Unsafe Workarounds

Never flush iptables or nftables. Docker depends on firewall and NAT rules for published ports and container connectivity, so flushing them can expand exposure or break networking. Do not publish ports 8000 or 5173 to bypass the Frontend, do not change the host default route, and do not delete Compose volumes or bind-mounted runtime data during network troubleshooting.

## Verification

After installation, verify `pja-br0`, the single exact pref 8999 rule, active/ enabled systemd state, healthy containers, localhost and private-address HTTP 200 responses, and a complete external TCP/HTTP exchange. Also verify Backend HTTPS still selects the existing Mihomo policy. A container restart and Frontend recreation must retain `pja-br0`; a server reboot is a separate, explicitly authorized validation step.
