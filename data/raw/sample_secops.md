# Incident Response Playbook (Sample)

## Goal
Turn messy ops notes into clean, reusable procedures with context.

## Triage Checklist
1) Identify affected hosts and users.
2) Capture volatile data (ps, netstat/ss, auth logs).
3) Snapshot configs + versions.

## Indicators
- suspicious domains: example.bad
- outbound spikes to unknown IP ranges

## Containment Steps
1) Isolate host (VLAN / firewall block).
2) Rotate credentials.
3) Preserve evidence.

## Notes
cookie newsletter subscribe (this line is here to test boilerplate scoring)

## Appendix
Command snippets:
  ss -lntp
  journalctl -u sshd --since "1 hour ago"
