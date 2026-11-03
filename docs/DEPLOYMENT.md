# GitHub Pages + scheduled publishing

This directory is the independent repository root. Do not publish the containing MoneyTalk repository.
1. Review the source-only release archive and license; create a new public code repository when approved.
2. Create a **separate private repository**, initialized with a README, for durable `voices.sqlite3` state.
   Never put the state database, raw sources, model.json or budget ledger in the public code repository.
3. GitHub Pages settings: source = GitHub Actions. Use the supplied `publish.yml` workflow.
4. Repository variables: `STATE_REPOSITORY=owner/private-state-repo`; `ENABLE_PUBLISH=true` only after review.
   Secrets: `STATE_DEPLOY_KEY`, an SSH deploy key with write access restricted to that private repository;
   `DEEPSEEK_API_KEY`, your own provider key. The Pages deployment uses the normal GITHUB_TOKEN.
5. Edit `examples/production.json` with verified current prices and your ticker whitelist. Never commit a key.
   Copy `examples/sources.json` into the private state repository as `sources.json` and review identities/rights there. The workflow reads that private registry; public defaults intentionally remain pending.
6. Prepare and approve at least six real backup editions locally; copy **only the selected new tool state** to
   the private repository as voices.sqlite3, then inspect private repository access. Do not copy all research data.
7. Dispatch the workflow with operation=export first. Inspect Pages and ensure no private artifacts are served.
   Then test tick; obtain a real due-window run with the local machine switched off before claiming offline operation.

Scheduled runner checks every 15 minutes, offset 7 minutes from the hour. XNYS calendar gates inference:
non-trading days and outside the two-hour recovery window do no production. Window receipts prevent duplicate
inference/publishing. Global workflow concurrency serializes all operations. One repository is the sole producer
of its private state; do not point multiple forks/workflows at the same ledger.

The workflow rejects public state repositories via metadata access; a metadata 404 is accepted only in conjunction with successful authenticated SSH checkout. Provisioning must verify private=true. The SSH deploy key grants access only to the state repository, never the personal account. It checkpoints budget reservations to that repository
**before every paid request**, and settles after usage returns. Every checkpoint failure aborts the paid request.
A crashed process leaves the maximum reservation charged conservatively. Do not restore an older ledger to
recover credits. A crashed window remains attempted; investigate and use explicit export/manual commands.

After every window, state is pushed before a Pages artifact is uploaded. If deployment fails, the previously
successful website stays live; dispatch export to retry the same edition without another model request.
No private logs or database are uploaded as public Actions artifacts. Pages artifacts contain approved static data only.
CI pull requests never receive production secrets. Production workflows are schedule/workflow_dispatch only.

**Permissions/gates:** configuring this template is not completed deployment. The maintainer must approve repository
visibility and contents, log in, create the repositories and add Secrets. Do not paste tokens into issues or screenshots.
GitHub schedules may be delayed or dropped; 15 minutes is an operational goal, not a guaranteed SLA.
If timeliness becomes contractual, replace the scheduler with a managed job service without changing content contracts.
Public-fork schedules can be disabled for inactivity; monitor workflow health and GitHub settings.

## First bounded trial

`TRIAL_WINDOW_ID=2026-11-03-post` restricts scheduled production to that one window.
Manual export still works. For recurring production, explicitly review and clear the trial variable.
The initial site contains one labeled historical selection; six real reserve editions are not yet prepared.
