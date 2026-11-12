# SmartNet Production Runbook

## Local development

1. Copy the root `.env.example` to `backend/.env`.
2. Keep `ENVIRONMENT=development`, `PAYMENT_DEMO_MODE=true` and
   `MIKROTIK_DEMO_MODE=true` only for local development.
3. Start the backend from the `backend` directory with
   `uvicorn app:app --reload --port 8000`.
4. Copy `frontend/.env.example` to `frontend/.env.local`, then run
   `npm install` and `npm run dev` from `frontend`.
5. Open `http://localhost:5173`. The first development administrator is created
   from `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` at backend startup. Change
   this password after login using the sidebar password-change action.
6. The optional Telegram bot runs from `backend` using
   `python -m bot.main_bot`. It requires a bot token and a JSON list of numeric
   administrator Telegram IDs.

## Production

Production requires the operator to supply provider and infrastructure values;
SmartNet does not invent payment endpoints, API keys or router credentials.

Required environment values:
- `ENVIRONMENT=production`
- unique random `SECRET_KEY` and `PAYMENT_WEBHOOK_SECRET` (32+ characters each)
- non-default `DASHBOARD_USERNAME` and strong unique `DASHBOARD_PASSWORD`
- unique `POSTGRES_PASSWORD` with at least 16 characters
- PostgreSQL `DATABASE_URL` using `postgresql+asyncpg://`
- `PAYMENT_PROVIDER_MODE=manual` for administrator-verified wallet/bank transfers, or `PAYMENT_PROVIDER_MODE=gateway` plus actual `PAYMENT_CHECKOUT_URL` and a provider-specific signature-verification adapter
- `PAYMENT_DEMO_MODE=false`
- `MIKROTIK_DEMO_MODE=false`, real router host/user/password/port
- exact HTTPS `CORS_ORIGINS`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` for Compose

1. Copy root `.env.example` to `.env` and replace every example value.
2. For manual wallet/bank transfer mode, use the private receipt review flow: an
   administrator checks the actual account, records manual payment verification,
   then approves the subscription. For gateway mode, configure a provider-specific
   adapter. The generic callback is only an internal trusted callback boundary;
   the adapter must validate the provider's signature, event uniqueness,
   registration reference, settled amount and currency.
3. Configure a least-privilege MikroTik API account and make the router reachable
   only over a VPN/private network. Do not expose RouterOS API ports publicly.
4. Review `SECURITY.md`, then deploy with `docker compose up -d --build`.
5. Verify `/api/health/ready`, login, permissions, router commands, payment callbacks,
   PDF storage and receipt privacy.
6. Take a database and uploads backup, then perform a restore test before launch.

## Important limitations

- The repository does not contain real payment-provider credentials or a provider-
  specific signature-verification adapter. Payment cannot be declared production
  ready until the selected provider is integrated and its sandbox/live flows pass.
- Live MikroTik operations require a reachable configured router and profiles that
  already exist on that router. Run a controlled acceptance test before serving users.
- Telegram is optional and only starts when the operator supplies a token and IDs.
- The initial Alembic baseline is intended for new databases. Existing PostgreSQL
  installations must be backed up and reviewed before migration.
