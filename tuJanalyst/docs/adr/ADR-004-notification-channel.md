# ADR-004: Report Notification Channel

| Field | Value |
|-------|-------|
| **Status** | Open |
| **Owner** | TBD |
| **Decision needed by** | Week 4 (T-407: Report Delivery depends on this) |
| **Affects tasks** | T-407, T-505 |

## Context

Layer 5 generates reports that need to reach the investment team. The MVP Definition says "email or Slack webhook." We need to pick one primary channel.

## Options

### Option A: Slack Webhook
- Simplest to implement: single HTTP POST with Block Kit formatted message
- Team already uses Slack (assumption — needs confirmation)
- Rich formatting: sections, fields, links, buttons
- Limitation: Slack messages have length limits (~3000 chars for blocks)
- Long reports need a "View full report" link back to the dashboard

### Option B: Email (SMTP)
- Universal — works regardless of team's chat tool
- No length limits — full report in the email body
- More setup: SMTP credentials, HTML email templates, deliverability concerns
- Harder to iterate on formatting

### Option C: Both (with primary/secondary)
- More code, more config, more things to break
- Unnecessary for an internal MVP with 2-3 users

## Recommendation

Slack webhook as primary. It's one HTTP call, rich formatting, and the team can discuss reports in-thread. Fall back to email only if the team doesn't use Slack.

## Decision

_Not yet decided. Confirm team's communication tool before Week 4._
