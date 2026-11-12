# SmartNet trusted network knowledge

## RouterOS API connectivity and least privilege
Use the official RouterOS API or REST API only across a private management network or VPN. Prefer API-SSL on TCP 8729 with a certificate that the SmartNet host trusts and verifies. Do not disable certificate or hostname validation to make a self-signed certificate work; install the issuing CA into the host trust store. Do not expose API ports directly to the public Internet. Create a dedicated RouterOS account with only the policies needed for the SmartNet use case. The read-only monitor should have read policy only.

Official references:
- https://manual.mikrotik.com/docs/developer-guides/api/
- https://manual.mikrotik.com/docs/developer-guides/rest-api/
- https://manual.mikrotik.com/docs/system-management/user/

## Hotspot user cannot authenticate
Start with read-only checks: confirm that the user account exists under IP > Hotspot > Users, that it is not disabled, and that its assigned profile exists. Compare the profile's intended shared-users and rate-limit settings with the service design. Check the Hotspot server, DHCP lease, DNS resolution and active/host tables before changing configuration. Never reset passwords or delete users as a diagnostic step.

Official references:
- https://manual.mikrotik.com/docs/
- https://manual.mikrotik.com/docs/user-guides/hotspot/

## Hotspot session is connected but browsing fails
Collect the active session's username, assigned address, uptime and byte counters. Check the DHCP lease, DNS service, gateway reachability and firewall/NAT counters. Separate a client Wi-Fi association problem from a RouterOS routing or upstream Internet problem. Record timestamps and measurements; do not claim an ISP outage without evidence.

Official references:
- https://manual.mikrotik.com/docs/
- https://manual.mikrotik.com/docs/network-management/dhcp/

## High CPU, memory pressure or intermittent instability
Record CPU load, free memory, uptime and RouterOS version before making changes. Compare measurements across several intervals. Review recent configuration changes and logs using read-only inspection. Avoid disabling firewall rules, rebooting, changing queues or upgrading RouterOS as an automated first response. Escalate a proposed change to a human operator with expected impact and rollback notes.

Official references:
- https://manual.mikrotik.com/docs/
- https://manual.mikrotik.com/docs/system-management/

## Safe handling of RouterOS changes
Changing a Hotspot profile, disconnecting users, changing firewall rules or rebooting can disrupt service. SmartNet must create a pending operation request, require an authorised administrator's approval, then execute the allow-listed action and write an audit event. Free-text chat and the diagnostic agent are read-only and must never execute RouterOS commands.
