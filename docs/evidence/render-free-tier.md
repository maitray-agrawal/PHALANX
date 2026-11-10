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

The resulting `X-Forwarded-For` header will be:

```
X-Forwarded-For: <real-client-ip>, <cloudflare-ip>
```

The **leftmost IP is the real client IP**.

**PHALANX setting required:**
```
TRUSTED_PROXY_COUNT=2
```

This tells `extract_client_ip()` to skip the two rightmost hops and return the
leftmost IP. Without this, the Cloudflare IP would be recorded as the client IP
and rate limiting would not isolate individual real clients.

> Source: Render networking documentation (render.com/docs/network-policies)
> and community documentation. The exact hop count is REPORTED, not directly
> verified from a live page fetch of render.com/docs/free.

## Render-Managed PostgreSQL (free — not used in PHALANX deploy)

PHALANX uses Neon for Postgres. Render's own free Postgres is listed here for
reference only.

| Attribute | Value |
|---|---|
| RAM | 256 MB |
| Storage | 1 GB |
| Auto-delete | ≤90 days after creation |
| Max free DBs/workspace | 1 |

## Regions

Available: Oregon (us-west), Ohio (us-east), Virginia (us-east), Frankfurt, Singapore.  
PHALANX `render.yaml` uses: **Oregon**.

## Notes for PHALANX

- `RECONCILER_ENABLED=false` is set in `render.yaml`; the in-process reconcile
  loop is disabled. Use `POST /v1/admin/reconcile-scheduled` with a Render Cron
  Job (or any external scheduler) instead.
- The filesystem is ephemeral, so in-memory webhook deduplication resets on
  every spin-down or deploy. This is documented in the README.
- `autoDeploy: false` is intentional; the CI workflow's deploy job calls the
  `RENDER_DEPLOY_HOOK` on every green push to `main`.

