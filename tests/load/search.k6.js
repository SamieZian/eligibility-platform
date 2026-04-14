// k6 load script — hits BFF searchEnrollments with bursty VU profile.
// Run: `k6 run tests/load/search.k6.js`
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    warmup: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '10s', target: 20 },
        { duration: '30s', target: 50 },
        { duration: '10s', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    http_req_failed: ['rate<0.01'],
  },
};

const QUERIES = ['sharma', 'patel', 'kaur', 'nair', 'priya'];

export default function () {
  const q = QUERIES[Math.floor(Math.random() * QUERIES.length)];
  const body = JSON.stringify({
    query: `{ searchEnrollments(filter: {q: "${q}"}, page: {limit: 25}) { total items { enrollmentId memberName } } }`,
  });
  const res = http.post('http://localhost:4000/graphql', body, {
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-Id': '11111111-1111-1111-1111-111111111111',
    },
  });
  check(res, {
    '200': (r) => r.status === 200,
    'has data': (r) => !!r.json('data.searchEnrollments'),
  });
  sleep(0.2);
}
