# Security and data boundaries

Do not open issues containing keys, production databases, raw private research or credentialed URLs.
If a credential is exposed, revoke it with its provider and remove it from all artifacts/history.
The static site has no model execution endpoints. Never expose a local management server publicly.
Production state belongs in a separate private repository with a dedicated, limited token.
Secrets are unavailable to pull-request CI; schedule/dispatch workflows require maintainer-controlled settings.
The maintainer has not yet designated a public security contact. Until then use the repository's private vulnerability reporting if enabled.
