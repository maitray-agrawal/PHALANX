# Render Free Tier — Evidence Record

**URL:** https://render.com/docs/free  
**Retrieved:** 2026-11-10 (via web search + official docs index)  
**Status:** REPORTED (search-indexed content; verify numbers on live page before hardcoding limits)

---

## Compute (Web Service — Free Plan)

| Attribute | Value |
|---|---|
| vCPU | 0.1 vCPU |
| RAM | 512 MB |
| Free instance hours/month | 750 hours per workspace (≈ 1 service running 24/7) |
| Sleep/spin-down | After **15 minutes** of no inbound HTTP traffic |
| Cold-start latency | ~**30–60 seconds** |
| Persistent disk | **Not available** — filesystem is ephemeral; wiped on restart, redeploy, and spin-down |
| SSL/TLS | Terminated at Render's load balancer; plain HTTP inside the container |
| Managed TLS cert | Provided for `*.onrender.com` and custom domains |
| Docker runtime | ✅ Supported on free tier |

## Proxy Hops (X-Forwarded-For)

Render's network routes requests through **two proxy hops** before reaching the container:

1. **Hop 1:** Cloudflare edge (DDoS / CDN layer)
2. **Hop 2:** Render's internal load balancer

The resulting `X-Forwarded-For` header arriving at the container will be:

```
X-Forwarded-For: <real-client-ip>, <cloudflare-ip>
```

In this header:
- `ips[-1]` is the `<cloudflare-ip>` (appended by Render's proxy).
- `ips[-2]` is the `<real-client-ip>` (appended by Cloudflare).
- The direct TCP peer (`request.client.host`) is Render's internal reverse proxy.

In PHALANX's `extract_client_ip`:
The index formula is `ips[-1 - trusted_count]`.
- With `TRUSTED_PROXY_COUNT=1`: `ips[-1 - 1] = ips[-2]` selects `<real-client-ip>`. If an attacker supplies a forged prefix (`<spoofed>, <client-ip>, <cloudflare-ip>`), `ips[-2]` correctly extracts `<real-client-ip>`.
- With `TRUSTED_PROXY_COUNT=2`: `ips[-1 - 2] = ips[-3]` would peel two positions left of `ips[-1]`, selecting an attacker's forged prefix (`ips[-3]`) if present.

**PHALANX setting configured in render.yaml:**
```
TRUSTED_PROXY_COUNT=1
FORWARDED_ALLOW_IPS=*
```

> Status: **UNVERIFIED**. Must be verified against the live hosted Render deployment by calling `GET /v1/admin/client-ip` with `X-Admin-Token` to inspect `raw_x_forwarded_for`, `tcp_peer`, and `resolved_client_ip`.

## Render-Managed PostgreSQL (free — not used in PHALANX deploy)

PHALANX uses Neon for Postgres. Render's own free Postgres is listed here for
reference only.

| Attribute | Value |
|---|---|
| RAM | 256 MB |
| Storage | 1 GB |
| Auto-delete | ≤90 days after creation |
| Max free DBs/workspace | 1 |

## Regions & Regional Alignment

Available Render Web Service regions:
- Oregon (`oregon` / US West)
- Ohio (`ohio` / US East)
- Virginia (`virginia` / US East)
- Frankfurt (`frankfurt` / EU)
- Singapore (`singapore` / Asia Pacific)

**Regional Alignment Rule:**
The Render web service region MUST be chosen to match your Neon database region to minimize network latency:
- If Neon database is created in AWS `us-west-2` (Oregon) -> Render `region: oregon` (default in `render.yaml`).
- If Neon database is created in AWS `us-east-2` (Ohio) -> Render `region: ohio`.

## External Cron Schedules

Because `RECONCILER_ENABLED=false` on free tier to conserve worker budget, configure external cron jobs (via cron-job.org, GitHub Actions, or Render Cron):

1. **Liveness / Keepalive Ping** (Every 10 minutes):
   - Target: `GET https://<your-render-url>/healthz`
   - Purpose: Prevents the 15-minute inactivity spin-down during active hackathon evaluation.
   - Note: `/healthz` touches NO database; returns `{ "status": "ok" }` in <2ms.

2. **Scheduled Reconcile Pass** (Every 30–60 minutes):
   - Target: `POST https://<your-render-url>/v1/admin/reconcile-scheduled`
   - Header: `X-Reconcile-Secret: <RECONCILE_SECRET>`
   - Purpose: Resolves ambiguous transaction holds and processes expired/pending states.
   - Rate limit: 5 requests/minute per caller IP.

3. **Daily Demo State Reset** (Every 24 hours at 00:00 UTC):
   - Target: `POST https://<your-render-url>/v1/admin/daily-reset`
   - Header: `X-Reconcile-Secret: <RECONCILE_SECRET>` (or `X-Admin-Token: <ADMIN_TOKEN>`)
   - Purpose: Restores demo budgets, resets step-up queues, and re-verifies ledger chain.

## Notes for PHALANX

- `RECONCILER_ENABLED=false` is set in `render.yaml`; the in-process reconcile
  loop is disabled. Use `POST /v1/admin/reconcile-scheduled` with a Render Cron
  Job (or any external scheduler) instead.
- The filesystem is ephemeral, so in-memory webhook deduplication resets on
  every spin-down or deploy. This is documented in the README.
- `autoDeploy: false` is intentional; the CI workflow's deploy job calls the
  `RENDER_DEPLOY_HOOK` on every green push to `main`.

