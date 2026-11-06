// k6 Soak Test: 30 VUs, 15 minutes
// Sustained execution to monitor memory leaks, connection pooling, and file descriptor stability.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 30 }, // Ramp up to 30 VUs
    { duration: '14m', target: 30 }, // Hold for 14 minutes
    { duration: '30s', target: 0 },  // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<300'], // p95 remains under 300 ms across the entire duration
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

  const idempotencyKey = `soak-${__VU}-${__ITER}-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
  const payload = JSON.stringify({
    agent_id: 'agent-auto-1',
    recipient_id: 'vendor_infra_aws',
    amount_minor: 1, // $0.01 to ensure budget doesn't exhaust over 15m
    currency: 'USD',
    purpose: 'Long-running Soak Traffic',
    idempotency_key: idempotencyKey,
  });

  const res = http.post(`${BASE_URL}/v1/payment-requests`, payload, { headers });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'decision is ALLOW': (r) => {
      try { return r.json().decision === 'ALLOW'; } catch (_) { return false; }
    },
  });

  // Interleave with read requests
  if (__ITER % 10 === 0) {
    const overviewRes = http.get(`${BASE_URL}/v1/overview`, { headers });
    check(overviewRes, {
      'overview status 200': (r) => r.status === 200,
    });
  }

  sleep(0.2);
}
