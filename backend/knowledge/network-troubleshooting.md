# SmartNet Network Troubleshooting Knowledge Base

This file is an operational summary, not a substitute for the official RouterOS manual.
The diagnostic agent is read-only and must never execute configuration or reboot commands.

## Evidence collection
- Use `/system/resource/print` for RouterOS version, board name, uptime, CPU load, total memory and free memory.
- Use `/ip/hotspot/active/print` to count authenticated HotSpot sessions and inspect reported session metadata.
- Compare multiple timestamped observations before calling an intermittent issue a persistent fault.
- Treat unavailable data as unknown; never convert a failed API call into a claim that the network is healthy.
- Active HotSpot session records include identity and network information. Keep detailed rows restricted to administrators.

## Interpreting symptoms
- High CPU load is a signal for further inspection, not proof of a specific cause. The official RouterOS Profiler can identify CPU use by process; capture it only during a controlled diagnostic window.
- Low free memory should be compared with the same router model and a historical baseline. Do not reboot solely because one sample is low.
- No active sessions may mean low demand, a captive-portal issue, failed authentication, or an observation failure. Confirm the API result and HotSpot server status before concluding.
- If the router is unreachable, first validate the private/VPN route, DNS/IP, firewall policy, API service state and least-privilege account. Never expose RouterOS API ports publicly.
- For HotSpot profile, authentication and session behavior, consult the official HotSpot documentation and compare against the live router configuration using read-only queries.

## Safe response rules
1. Report observation timestamp, router identity/version and missing metrics.
2. Separate measured facts from possible causes.
3. Suggest reversible read-only checks first.
4. Do not issue `/system reboot`, configuration `set`, `add`, `remove`, or any other mutation.
5. Any later change must become a network action request and pass administrator approval through SmartNet.

## Primary references
- RouterOS official documentation: https://manual.mikrotik.com/docs/
- RouterOS system resource (CPU/memory/version metrics): https://help.mikrotik.com/docs/spaces/ROS/pages/40992875/Resource
- RouterOS HotSpot (profiles, users and active sessions): https://help.mikrotik.com/docs/spaces/ROS/pages/56459266/HotSpot+-%2B+Captive+portal
- RouterOS Profiler: https://help.mikrotik.com/docs/spaces/ROS/pages/8323153/Profiler
- RouterOS REST API security guidance: https://help.mikrotik.com/docs/spaces/ROS/pages/47579162/REST+API
