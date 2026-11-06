// k6 Stress Test: Ramp until p95 > 500ms or error rate > 1%
// Determines breaking point and maximum sustainable capacity.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 },
    { duration: '30s', target: 100 },
    { duration: '30s', target: 150 },
    { duration: '30s', target: 200 },
    { duration: '30s', target: 250 },
    { duration: '30s', target: 300 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    // Stress target: observe when latency or error threshold breaks
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
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

  const idempotencyKey = `stress-${__VU}-${__ITER}-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
  const payload = JSON.stringify({
    agent_id: 'agent-auto-1',
    recipient_id: 'vendor_infra_aws',
    amount_minor: 1,
    currency: 'USD',
    purpose: 'Infrastructure Stress Test',
    idempotency_key: idempotencyKey,
  });

  const res = http.post(`${BASE_URL}/v1/payment-requests`, payload, { headers });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'decision is ALLOW': (r) => {
      try { return r.json().decision === 'ALLOW'; } catch (_) { return false; }
    },
  });

  sleep(0.05);
}
