# AI backend setup

The desktop now calls this backend for existing analysis and email drafting. It has no local-provider fallback. Until configured, AI requests fail closed; local reading, saved data and manual email editing remain available.

1. Apply `supabase/migrations/202609130003_ai_allowances.sql` to the existing project.
2. On the backend host, configure `GEMINI_API_KEY`, `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (or use `backend/.env`). Keep provider credentials off the desktop and out of git. No service-role key is required.
3. In Supabase SQL Editor, explicitly grant each desired user a feature allowance. There are no invented plan tiers or automatic grants:

```sql
-- Substitute the actual authenticated user UUID and the monthly request limit you choose.
insert into public.ai_allowances(user_id, feature, enabled, monthly_limit)
values ('USER_UUID', 'email_drafting', true, 100)
on conflict(user_id,feature) do update set enabled=excluded.enabled, monthly_limit=excluded.monthly_limit;
-- Grant document_analysis separately to preserve access to document/context explanations.
```

4. Install `pip install -r backend/requirements.txt` on a Python 3.11 backend host and run `python -m uvicorn backend.api:app --host 127.0.0.1 --port 8080 --no-access-log`, behind an HTTPS reverse proxy. Do not enable request/body/header logging at the proxy. The provider deadline is 45 seconds; the desktop deadline is 65 seconds. Requests are not automatically retried: failed provider attempts consume a request allowance and the user explicitly retries.
5. Set `AMILLUM_AI_BACKEND_URL=https://YOUR_BACKEND` in the desktop `.env`, and restart Amillum. Remove provider keys from the desktop `.env`; that file should contain only the public Supabase configuration and backend URL.

`POST /v1/generate` uses the Supabase user bearer token. Supported features are `document_analysis` and `email_drafting`. The backend verifies identity and atomically consumes the feature allowance before calling the existing analysis engine. Unknown/disabled features and exhausted quotas are denied. Allowance and usage rows are owner-readable, not client-writable, and cascade on account deletion.

Email handoff opens the default macOS mail application's editable composer. Amillum never sends email. The user must confirm the handoff and then send from the mail application. No OAuth integration is installed.

## Container deployment and checks

From the repository root, build `docker build -f backend/Dockerfile -t amillum-ai .`.
Deploy this image to an HTTPS container host. Set the three backend environment variables above in the host secret/environment settings. The container runs as a non-root user and listens on `PORT` (default 8080). The build context is allowlisted and contains no `.env`, desktop assets, tests, or user data.

Use `/healthz` for liveness. `/readyz` returns 200 only when public Supabase configuration and the provider key are present; it does not claim database grants or upstream connectivity are verified. Neither endpoint consumes allowance or calls AI. Missing configuration rejects generation before consuming allowance. Disable request/header/body logging in the hosting proxy, and allow responses to take at least 65 seconds.

The allowance migration can be reapplied without deleting existing grants or usage. Apply it through the existing migration system; it does not grant any user access automatically. Verify both `email_drafting` and `document_analysis` grants for the intended authenticated user. Never put operator credentials in the desktop.

For source-only local development, run the backend on loopback with the command above and set `AMILLUM_ENV=development` plus `AMILLUM_AI_BACKEND_URL=http://127.0.0.1:8080` in the desktop environment. Production defaults to HTTPS; packaged builds reject HTTP even with development selected. For production set `AMILLUM_ENV=production` and the deployed HTTPS URL, then restart the desktop. Do not ship a loopback URL.

Before declaring production connected, check deployed health/readiness, sign in through Amillum, generate a draft from a deliberately approved nonsensitive excerpt, edit/regenerate/cancel, and confirm an editable mail-app handoff without sending. Verify an exhausted allowance is rejected and existing document analysis is enabled. Local mocked tests do not replace these live checks.

## M15A–G: website billing (no deployment provider selected)

Apply `supabase/migrations/202609140001_monetization.sql` after the existing migrations. Then run `python -m backend.catalog` and apply its generated SQL in Supabase SQL Editor. `backend/config/plans.json` is the canonical catalog; repeat the catalog seed when changing limits or marketing data. Clients only read the deployed catalog. Existing M15 usage rows are retained; `ai_allowances` is retained as legacy data and no longer authorizes requests. Access now comes from plans and verified subscription state.

Free resets monthly (UTC). Paid plans use Stripe billing periods; trials use their own period. Active plan changes carry usage across interval changes. Trial-to-paid conversion starts a new allowance. Failed payment or expired periods fall back to Free; paid access never survives an expired trusted period. Existing Workbench items remain readable/editable/deletable above a downgraded cap; new items are blocked. The catalog explicitly marks unimplemented premium features as planned, never available.

Set the billing variables in `backend/.env.example` on the backend only. `SUPABASE_SERVICE_ROLE_KEY` is required only for Stripe customer mapping and subscription synchronization. Never ship that file/module or key with the desktop or website. The website needs only its backend URL and a long random `WEBSITE_SESSION_SECRET`; its `.env.example` documents these. Website sessions keep access/refresh tokens in server memory, with only an opaque session ID in signed browser storage. A website restart requires sign-in again; use one website process for this initial implementation.

In Stripe test mode create exactly three USD recurring prices: Weekly $5/week, Monthly $24/month, Grand $35/week. Set the corresponding `STRIPE_PRICE_*` values. Configure the Customer Portal to allow these prices, payment/invoice management, cancellation, and subscription updates; choose and disclose proration and downgrade timing there. Amillum follows Stripe's confirmed state. The backend verifies Checkout price amounts/intervals against the catalog. New paid subscribers get one 7-day trial with a payment method; trial eligibility is consumed when Checkout is reserved, including abandoned Checkout. Checkout reservations expire after 31 minutes. No client or local file can restore eligibility. The account must remain until a subscription is effectively canceled, to avoid orphaned recurring billing.

Register `/v1/stripe/webhook` for `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `checkout.session.completed`, `invoice.paid`, and `invoice.payment_failed`. Pin webhook/API version to `2025-03-31.basil`. Store its signing secret server-side. Set `STRIPE_MODE=test` until live verification. Webhooks require signed raw bodies within five minutes and the configured mode. They fetch current Stripe state and reject older state updates. Unknown prices/customer mappings fail closed for retry. Configure Stripe retries and monitor delivery failures without logging request bodies or tokens.

Set `AMILLUM_WEBSITE_URL` and all three Stripe return URLs to the same HTTPS website origin in production. For localhost use explicit `AMILLUM_ENV=development`. Set the desktop website URL too. The website `/pricing`, `/signin`, `/account`, and `/download` own customer billing and onboarding; desktop links lead there. No website or desktop state grants access. A missing catalog/backend/configuration fails closed.

Before production: apply/seed SQL, verify RLS, configure test prices/portal/webhooks, sign into the same Supabase account on website and desktop, complete test Checkout, observe trial/usage, exercise portal plan changes/cancellation and payment failure, then explicitly confirm an editable email handoff without sending. Verify live-mode configuration separately before accepting payments. No hosting provider is selected or deployed by this milestone.
