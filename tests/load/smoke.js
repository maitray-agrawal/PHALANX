// k6 Smoke Test: 1 VU, 1 minute
// Verifies baseline functionality and latency under minimal load.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '1m',
  thresholds: {
    http_req_duration: ['p(95)<300'], // p95 under 300 ms
    http_req_failed: ['rate<0.001'],   // Error rate under 0.1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://phalanx-api:8000';

export function setup() {
  let token = __ENV.AUTH_TOKEN;
  if (!token) {
    const res = http.post(`${BASE_URL}/v1/auth/demo-token`, JSON.stringify({
      role: 'agent',
      agent_id: 'agent-auto-1',
    }), {
      headers: { 'Content-Type': 'application/json' },
    });
    check(res, { 'auth token obtained': (r) => r.status === 200 });
    token = res.json().access_token;
  }
  return { token };
}

export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // 1. Submit an authorized instant payment request
  const idempotencyKey = `smoke-${__VU}-${__ITER}-${Date.now()}`;
  const payload = JSON.stringify({
    agent_id: 'agent-auto-1',
    recipient_id: 'vendor_infra_aws',
    amount_minor: 1, // $0.01
    currency: 'USD',
    purpose: 'Cloud Infrastructure Hosting',
    idempotency_key: idempotencyKey,
  });

  const res = http.post(`${BASE_URL}/v1/payment-requests`, payload, { headers });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'decision is ALLOW': (r) => {
      try { return r.json().decision === 'ALLOW'; } catch (_) { return false; }
    },
    'request_state is SETTLED': (r) => {
      try { return r.json().request_state === 'SETTLED'; } catch (_) { return false; }
    },
  });

  // 2. Query system overview
  const overviewRes = http.get(`${BASE_URL}/v1/overview`, { headers });
  check(overviewRes, {
    'overview status 200': (r) => r.status === 200,
  });

  sleep(0.5);
}
