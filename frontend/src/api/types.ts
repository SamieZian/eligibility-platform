// Shapes mirror services/bff/app/schema.py — keep in sync or break CI.

export type SortOrder = 'effective_date_desc' | 'effective_date_asc';

export interface Enrollment {
  enrollmentId: string;
  tenantId: string;
  employerId: string;
  employerName: string | null;
  planId: string;
  planName: string | null;
  planCode: string | null;
  memberId: string;
  memberName: string;
  firstName: string;
  lastName: string;
  dob: string | null;
  gender: string | null;
  cardNumber: string | null;
  ssnLast4: string | null;
  relationship: string;
  status: string;
  effectiveDate: string;
  terminationDate: string;
}

export interface TimelineSegment {
  id: string;
  planId: string;
  planName: string | null;
  status: string;
  validFrom: string;
  validTo: string;
  txnFrom: string;
  txnTo: string;
  isInForce: boolean;
  sourceFileId: string | null;
  sourceSegmentRef: string | null;
}

export interface FileJob {
  id: string;
  fileId: string;
  objectKey: string;
  format: string;
  status: string;
  uploadedAt: string;
  totalRows: number | null;
  successRows: number | null;
  failedRows: number | null;
}

export interface EmployerSummary {
  id: string;
  name: string;
  externalId: string | null;
  payerId: string | null;
}

export interface SearchResult {
  items: Enrollment[];
  total: number;
  nextCursor: string | null;
}

export interface SearchFilter {
  q?: string | null;
  cardNumber?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  ssnLast4?: string | null;
  employerId?: string | null;
  employerName?: string | null;
  subgroupName?: string | null;
  planName?: string | null;
  planCode?: string | null;
  dob?: string | null;
  effectiveDateFrom?: string | null;
  effectiveDateTo?: string | null;
  terminationDateFrom?: string | null;
  terminationDateTo?: string | null;
  memberType?: string | null;
  status?: string | null;
}

export interface Page {
  limit: number;
  cursor?: string | null;
  sort?: SortOrder;
}

export interface UploadResponse {
  file_id: string;
  job_id: string;
  status: string;
}
