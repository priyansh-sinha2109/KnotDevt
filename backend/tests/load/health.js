import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '10s',
  thresholds: {
    checks: ['rate==1'],
    http_req_failed: ['rate==0'],
  },
};

export default function () {
  const base = 'http://127.0.0.1:8080';
  const liveness = http.get(base + '/api/v1/health');
  const readiness = http.get(base + '/health/ready');
  check(liveness, { 'liveness returns 200': (r) => r.status === 200 });
  check(readiness, {
    'readiness confirms PostgreSQL and Redis': (r) =>
      r.status === 200 && r.json('postgres') === true && r.json('redis') === true,
  });
  sleep(0.05);
}
