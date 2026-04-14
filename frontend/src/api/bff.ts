import { GraphQLClient, gql } from 'graphql-request';
import type {
  EmployerSummary,
  Enrollment,
  FileJob,
  Page,
  SearchFilter,
  SearchResult,
  TimelineSegment,
  UploadResponse,
} from './types';

const BASE_URL = (import.meta.env.VITE_BFF_URL as string | undefined) ?? 'http://localhost:4000';
const GRAPHQL_URL = `${BASE_URL.replace(/\/$/, '')}/graphql`;
const REST_URL = BASE_URL.replace(/\/$/, '');

function newCorrelationId(): string {
  const rnd = () => Math.random().toString(36).slice(2, 10);
  return `cid-${Date.now().toString(36)}-${rnd()}`;
}

function getTenantId(): string {
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem('bff.tenantId');
    if (stored) return stored;
  }
  return '11111111-1111-1111-1111-111111111111';
}

let lastCorrelationId = '';
export function getLastCorrelationId(): string {
  return lastCorrelationId;
}

function buildHeaders(): Record<string, string> {
  const cid = newCorrelationId();
  lastCorrelationId = cid;
  return {
    'X-Tenant-Id': getTenantId(),
    'X-Correlation-Id': cid,
    'Content-Type': 'application/json',
  };
}

function client(): GraphQLClient {
  return new GraphQLClient(GRAPHQL_URL, { headers: buildHeaders() });
}

const SEARCH = gql`
  query Search($filter: SearchFilter, $page: Page) {
    searchEnrollments(filter: $filter, page: $page) {
      items {
        enrollmentId
        tenantId
        employerId
        employerName
        planId
        planName
        planCode
        memberId
        memberName
        firstName
        lastName
        dob
        gender
        cardNumber
        ssnLast4
        relationship
        status
        effectiveDate
        terminationDate
      }
      total
      nextCursor
    }
  }
`;

const MEMBER_BY_CARD = gql`
  query MemberByCard($cardNumber: String!) {
    memberByCard(cardNumber: $cardNumber) {
      enrollmentId
      memberId
      memberName
      firstName
      lastName
      cardNumber
      dob
      employerName
      planName
      status
      effectiveDate
      terminationDate
      relationship
    }
  }
`;

const TIMELINE = gql`
  query Timeline($memberId: ID!) {
    enrollmentTimeline(memberId: $memberId) {
      id
      planId
      planName
      status
      validFrom
      validTo
      txnFrom
      txnTo
      isInForce
      sourceFileId
      sourceSegmentRef
    }
  }
`;

const FILE_JOB = gql`
  query Job($fileId: ID!) {
    fileJob(fileId: $fileId) {
      id
      fileId
      objectKey
      format
      status
      uploadedAt
      totalRows
      successRows
      failedRows
    }
  }
`;

const EMPLOYERS = gql`
  query Employers($search: String) {
    employers(search: $search) {
      id
      name
      externalId
      payerId
    }
  }
`;

const TERMINATE = gql`
  mutation Terminate($memberId: ID!, $planId: ID!, $validTo: Date!) {
    terminateEnrollment(memberId: $memberId, planId: $planId, validTo: $validTo)
  }
`;

const REPLAY = gql`
  mutation Replay($fileId: ID!) {
    replayFile(fileId: $fileId)
  }
`;

export async function searchEnrollments(filter: SearchFilter, page: Page): Promise<SearchResult> {
  const { searchEnrollments } = await client().request<{ searchEnrollments: SearchResult }>(SEARCH, {
    filter,
    page,
  });
  return searchEnrollments;
}

export async function memberByCard(cardNumber: string): Promise<Enrollment | null> {
  const { memberByCard } = await client().request<{ memberByCard: Enrollment | null }>(MEMBER_BY_CARD, {
    cardNumber,
  });
  return memberByCard;
}

export async function enrollmentTimeline(memberId: string): Promise<TimelineSegment[]> {
  const { enrollmentTimeline } = await client().request<{ enrollmentTimeline: TimelineSegment[] }>(
    TIMELINE,
    { memberId },
  );
  return enrollmentTimeline;
}

export async function fileJob(fileId: string): Promise<FileJob | null> {
  const { fileJob } = await client().request<{ fileJob: FileJob | null }>(FILE_JOB, { fileId });
  return fileJob;
}

export async function employers(search?: string): Promise<EmployerSummary[]> {
  const { employers } = await client().request<{ employers: EmployerSummary[] }>(EMPLOYERS, { search });
  return employers;
}

export async function terminateEnrollment(
  memberId: string,
  planId: string,
  validTo: string,
): Promise<string[]> {
  const { terminateEnrollment } = await client().request<{ terminateEnrollment: string[] }>(TERMINATE, {
    memberId,
    planId,
    validTo,
  });
  return terminateEnrollment;
}

export async function replayFile(fileId: string): Promise<boolean> {
  const { replayFile } = await client().request<{ replayFile: boolean }>(REPLAY, { fileId });
  return replayFile;
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const cid = newCorrelationId();
  lastCorrelationId = cid;
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${REST_URL}/files/eligibility`, {
    method: 'POST',
    headers: {
      'X-Tenant-Id': getTenantId(),
      'X-Correlation-Id': cid,
    },
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status} ${res.statusText}`);
  return (await res.json()) as UploadResponse;
}

export const __test__ = { GRAPHQL_URL, REST_URL, buildHeaders };
