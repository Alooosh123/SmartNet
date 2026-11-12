# SmartNet Security and Production Gate

## Immediate actions for this repository

The repository has previously contained a SQLite database, uploaded receipt/image files,
generated PDFs and Python bytecode. Removing those files from the current tree does not
remove them from Git history. Treat any credentials, customer data or payment evidence
that may have been committed as exposed:

1. Rotate the JWT signing key, payment webhook secret, router password and any provider keys.
2. Review Git history and repository forks/caches. If personal data or secrets were committed,
   perform a coordinated history rewrite and revoke old credentials.
3. Do not reuse any real password or payment key from the repository.
4. Keep receipts private. The API now serves receipt files only to authenticated administrators.

## Production configuration

Set `ENVIRONMENT=production`. Application startup rejects default secrets, demo payment,
demo MikroTik mode, SQLite and non-HTTPS CORS origins. Generate distinct random secrets of
at least 32 characters for `SECRET_KEY` and `PAYMENT_WEBHOOK_SECRET`.

Use PostgreSQL with a unique strong database password, HTTPS behind a reverse proxy, a
private/VPN route to the MikroTik API and a least-privilege RouterOS account. The supplied
Nginx config rate-limits login, registration and receipt uploads; retain equivalent limits
if another reverse proxy is used. Do not expose RouterOS API ports to the public internet.

## Payment integration boundary

The generic callback endpoint authenticates a shared-secret channel and marks a registration
as paid-pending-review. It does not independently verify a provider signature, event ID,
settled amount or currency. A real provider adapter must verify all of those fields with the
provider's official documentation/API before calling the internal callback. Never treat a
receipt image as payment proof. An administrator must approve the registration after review.

## Operational controls

- Run Alembic migrations before deploying new backend code.
- Use a managed secrets store or protected environment variables.
- Apply reverse-proxy rate limits to login, registration, payment and upload endpoints.
- Back up PostgreSQL and private uploads; test restore procedures.
- Monitor application logs, failed payment callbacks and MikroTik connectivity.
- Keep the admin bootstrap password private, then change it after first deployment using the authenticated «تغيير كلمة المرور» action or `POST /auth/change-password`.
- Run CI and security tests before deployment.
