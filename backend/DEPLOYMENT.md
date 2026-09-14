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

## Railway

Create a Railway project/service from this repository, with repository root `/` (not `/backend`). The root `railway.json` selects `backend/Dockerfile`, uses `/readyz` for deployment health, and honors Railway's `PORT`. Do not override the start command.

In service Variables set `GEMINI_API_KEY`, `SUPABASE_URL`, and `SUPABASE_PUBLISHABLE_KEY`. Enter secrets in Railway directly, never commit them. Deploy, then use service Settings → Networking → Generate Domain to obtain the HTTPS URL. Check `/healthz` and `/readyz` on that domain. Set the desktop `AMILLUM_AI_BACKEND_URL` to that URL, without `/v1/generate`, and `AMILLUM_ENV=production`. Restart Amillum.

Before the live generation check, apply the allowance SQL in Supabase and grant the intended user's two features as described above. No schema deployment is performed automatically using privileged credentials.

Railway configuration reference: https://docs.railway.com/config-as-code/reference
