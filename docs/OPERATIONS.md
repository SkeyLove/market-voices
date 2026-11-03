# Operations and five-session trial

## Before launch

- Use `status` to inspect mode, backup inventory (target >=6), windows and conservative model costs.
- Clear source identities and reuse scope; confirm paragraphs/subtitles, not titles, support the summaries.
- Validate an actual screenshot in Chinese and English, keyboard navigation, desktop and 375px viewport.
- Verify artifacts contain no raw bodies, API keys, local paths, database, state or budget data.
- Start with a bounded source set. A source listed in configuration is not a successfully covered source.

## Each scheduled window

The private event log records collection outcome, generated/failed summaries, approval, publishing delay and mode changes.
Track input count, retrieval success, source publication age, per-accepted-item estimated CNY, manual editing time,
automatic publication rate and reserve usage separately. Model costs exclude human time, Codex subscription,
Actions limits and domain expenses. Check actual provider invoices against conservative estimates.

401/402/403: stop all further inference for the same credentials; verify credentials/account through the provider UI. Changing credentials clears the match; after a balance refill use `reset-provider` explicitly. Never log the key.
429/5xx/transport failure: at most one automatic retry per content fingerprint and within budget.
Invalid quotes/translations/identity: keep pending; correct with Skill or human editing and re-import.
Budget exhausted/expired rates: no new paid calls; publish an approved reserve or mark delayed.
After three failed/no-new-content windows: mode becomes manual. Auto recovery requires explicit operator action.
A healthy but quiet day can therefore also trigger manual mode; this conservative first version is deliberate.

## Trial record (must be filled with actual observations)

For five **actual trading sessions**, record both pre/post window IDs, target and actual time, mode,
source successes/attempts, new/accepted/failed items, estimated cost, human edit minutes, reserve consumption,
website URL and reader-visible freshness. Include one window with local machine off. Do not backdate runs.
The repository includes executable tests of calendar cases, not five actual days of operation.

## User study

Recruit 3–5 consenting target readers yourself. Have each (1) find one person's NVDA view,
(2) compare two differing views, (3) open original evidence, (4) identify whether an item is current or historical,
(5) change language and assess consistency. Record completion, time, misunderstandings, quotes (with consent)
and concrete proposed changes. No participants or feedback have been supplied yet; do not invent them.

## Publication integrity

Approval is hash-bound and local to this tool. A database owner can change it; it is an audit trail, not a digital signature.
Publication snapshots stay immutable; withdrawal is applied to every exported archive. Re-export and redeploy after withdrawal.
Unknown institution/personal aliases must be assigned to the same independent group before approval.
Statistics describe the tracked sample only. Never label them whole-market sentiment or expected returns.

The CNY cap is enforced against the configured conservative rate/exchange conversion, not a provider-enforced
account spending limit. Update prices on changes and compare real bills; other applications using the same
API key are outside this ledger. Do not share a key/state ledger among uncontrolled producers.
