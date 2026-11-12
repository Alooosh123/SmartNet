# SmartNet Security and Production Gate

## Production requirements

- Use MariaDB 12.3 LTS via SQLAlchemy asyncmy. Never expose port 3306 publicly.
- Use Podman/Podman Compose, preferably rootless. Containerfiles run as non-root where supported.
- Set unique JWT and webhook secrets (32+ characters), non-default admin credentials, and separate 24+ character MariaDB application/root passwords.
- Use HTTPS at the reverse proxy, exact HTTPS CORS origins and private persistent storage for receipts/PDFs.
- Connect to MikroTik over VPN/private networking and API-SSL 8729 with certificate verification enabled.
- Use separate RouterOS identities: observer read-only; controller for explicitly approved changes.
- Production currently allows manual payment verification only. Receipt upload never means payment has arrived.

## Manual payment integrity

The administrator checks actual funds outside SmartNet, then records exact amount, currency, method and unique reference. The amount must match the subscription request. A ManualPayment record is separate from subscription activation. A second explicit admin approval activates the account. Reconciliation identifies paid or activated requests without matching manual payment records.

A provider gateway is not complete until a provider-specific adapter validates its documented signature, event ID, invoice reference, settlement status, amount and currency, with idempotent processing. A shared-secret callback alone is not sufficient.

## Network agent safety

- Network Observer reads telemetry only using its separate RouterOS read-only user.
- Diagnostic Agent uses curated knowledge and returns recommendations; it has no RouterOS write API.
- Network actions are expiring requests. A different administrator must approve a requested admin operation before router execution.
- Do not give generic shell execution or RouterOS credentials to an LLM.

## Backups and recovery

- Keep MariaDB dumps and private uploads/PDFs together in encrypted off-host backups.
- Run a restore rehearsal on a separate MariaDB target and verify login, subscriptions, payment references and PDF retrieval.
- Restore scripts require explicit confirmation because restore replaces current records/files.

## Vulnerability management

- CI runs pip-audit and npm audit and fails on disclosed dependency advisories.
- Dependabot checks Python, npm and GitHub Actions dependencies weekly.
- Review upgrades and the full CI/browser test result before merging.

## Repository history hygiene

The repository previously contained SQLite databases, uploaded receipt/image files, generated PDFs and bytecode. Removing these from the current branch does not remove them from Git history, forks or caches. Treat any credentials or personal/payment data committed in the past as exposed:
1. Rotate JWT, webhook, router, provider, Telegram and AI keys.
2. Review history and forks/caches; coordinate a history rewrite if secrets or personal data were committed.
3. Never reuse an old secret from Git.
4. Never commit .env, databases, receipts, exported PDFs or production backups.
