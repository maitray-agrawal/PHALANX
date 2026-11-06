// k6 Single-Budget Contention Test: 100 VUs on ONE budget
// Validates concurrency control, PostgreSQL row-level locks, and zero deadlocks.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    contention: {
      executor: 'constant-vus',
      vus: 100,
      duration: '45s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<400'], // p95 under 400 ms under intense lock contention
    http_req_failed: ['rate<0.001'],   // 0% failures (no deadlocks or 500 errors)
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

  // Every VU hits the EXACT same agent_id and budget concurrently
  const idempotencyKey = `contention-${__VU}-${__ITER}-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
  const payload = JSON.stringify({
    agent_id: 'agent-auto-1',
    recipient_id: 'vendor_infra_aws',
    amount_minor: 1, // $0.01
    currency: 'USD',
    purpose: 'Budget Contention Test',
    idempotency_key: idempotencyKey,
  });

  const res = http.post(`${BASE_URL}/v1/payment-requests`, payload, { headers });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'decision is ALLOW': (r) => {
      try { return r.json().decision === 'ALLOW'; } catch (_) { return false; }
    },
  });

  sleep(0.02);
}

