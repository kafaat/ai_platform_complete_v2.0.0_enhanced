# SAHOOL Static Event/NATS Contract Report

## Scope

Conservative static inventory of literal NATS/JetStream subjects (a name argument is resolved only from a loop over a module-level tuple of literals, or a single local f-string whose placeholders fill whole tokens, rendered as `*`). Dynamic subjects are listed but are not used to declare missing producers or consumers.

## Summary

| Metric | Value |
|---|---:|
| Python files scanned | 1227 |
| Resolved literal contracts | 4 |
| Dynamic contracts | 14 |
| Unique literal subjects | 4 |
| Matched subjects | 0 |
| Producer-only subjects | 1 |
| Consumer-only subjects | 3 |
| Cross-component duplicate durables | 0 |
| Runtime verified | No |
| Production certified | No |

## Review boundary

Producer-only and consumer-only entries are review candidates, not automatic defects. They can represent external integrations, future consumers, generic publishers, or dynamic subject construction.
