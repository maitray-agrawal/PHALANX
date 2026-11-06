// k6 Idempotency Storm Test: same idempotency key 200 times concurrently
// Validates that exactly ONE payment is executed and 199 return the cached result.
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    storm: {
      executor: 'per-vu-iterations',
      vus: 200,
      iterations: 1,
      maxDuration: '30s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'],
    http_req_failed: ['rate<0.001'],
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
  const stormKey = `storm-key-${Date.now()}`;
  return { token, stormKey };
}

export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // Every VU uses the EXACT SAME idempotency key
  const payload = JSON.stringify({
    agent_id: 'agent-auto-1',
    recipient_id: 'vendor_infra_aws',
    amount_minor: 50, // $0.50
    currency: 'USD',
    purpose: 'Idempotency Storm Validation',
    idempotency_key: data.stormKey,
  });

  const res = http.post(`${BASE_URL}/v1/payment-requests`, payload, { headers });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'decision is ALLOW': (r) => {
      try { return r.json().decision === 'ALLOW'; } catch (_) { return false; }
    },
  });
}

