# Shared content contract

Run `market-voices candidates --output /private/path/new.json` for actual inputs.
A summary import is an array of `{"id": "raw record id", "summary": {...}}`.
Fields: `title_zh`, `title_en`, `summary_zh`, `summary_en`, `speaker_id`, `ticker`,
`stance` (bullish/neutral/bearish/conditional/unclear), `horizon` (unspecified/short_term/long_term),
`quote`, `conditions_zh`, `conditions_en`, `input_hash`, `method` (skill/api/demo),
`producer`, `prompt_version` (voices-summary.v1), `generated_at` (optional aware ISO timestamp).

The authoritative fingerprint is
`input_hash` exposed at the candidate root. It hashes content plus prompt version;
copy it, do not recompute it by hand. Both API and Skill imports use the same
Pydantic types and evidence checks. Summary import does not approve publication.

Identity belongs to registered `Source`, not model output. Each source has a stable
speaker_id and independent group. Multiple accounts of one institution share a group.
No source can auto-publish until verified=true and rights is summary_link_only or licensed.
The operator must verify those fields; the sample registry deliberately remains pending.

Raw evidence is full_text/transcript/official_text/feed_excerpt/summary_only/title_only/unavailable.
Only the first three enter approved editions. An excerpt is never silently promoted to full text.
Quote is 20–500 characters and must match source words after stripping numeric timestamp
markers and folding whitespace. This is a mechanical guard, not proof that a conclusion follows.
Manual review and the human evaluation set assess actual meaning and translation fidelity.

Approval binds the complete summary hash. Editing text, identity, date, conditions or
prompt version invalidates eligibility. Content approval is separate from edition approval.
Original dates, publication dates and synthetic labels remain separate in the public feed.

`voices.public.v1` contains whitelisted publication fields, server-produced counts,
coverage metadata and archive references. It never contains raw body text, API keys,
private diagnostics, budget data or local filesystem paths.
