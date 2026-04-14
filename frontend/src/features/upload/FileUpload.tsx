import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fileJob, uploadFile } from '../../api/bff';
import { Button } from '../../components/Button';
import { Spinner } from '../../components/Spinner';
import { useLocalStorage } from '../../lib/useLocalStorage';
import styles from './FileUpload.module.css';

interface RecentUpload {
  fileId: string;
  fileName: string;
  at: string;
}

const TERMINAL = new Set(['COMPLETED', 'PARTIAL_SUCCESS', 'FAILED_FORMAT', 'FAILED_BUSINESS']);

export function FileUpload() {
  const [selected, setSelected] = useState<File | null>(null);
  const [recent, setRecent] = useLocalStorage<RecentUpload[]>('bff.uploads', []);
  const [trackingId, setTrackingId] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (f: File) => uploadFile(f),
    onSuccess: (resp) => {
      setTrackingId(resp.file_id);
      setRecent((prev) => [
        { fileId: resp.file_id, fileName: selected?.name ?? '', at: new Date().toISOString() },
        ...prev.filter((r) => r.fileId !== resp.file_id),
      ].slice(0, 10));
    },
  });

  const { data: job } = useQuery({
    queryKey: ['fileJob', trackingId],
    queryFn: () => (trackingId ? fileJob(trackingId) : Promise.resolve(null)),
    enabled: !!trackingId,
    refetchInterval: (q) => {
      const status = (q.state.data as { status?: string } | null | undefined)?.status;
      return status && TERMINAL.has(status) ? false : 2000;
    },
  });

  return (
    <div className={styles.wrap}>
      <h1>Upload Eligibility File</h1>
      <p className={styles.hint}>Accepts .x12 (ANSI 834), .csv, .xlsx. Files stream to MinIO and the ingestion worker consumes them asynchronously.</p>

      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          if (selected) upload.mutate(selected);
        }}
      >
        <input
          type="file"
          accept=".x12,.csv,.xlsx"
          onChange={(e) => setSelected(e.target.files?.[0] ?? null)}
          aria-label="Select file"
        />
        <Button type="submit" disabled={!selected || upload.isPending}>
          {upload.isPending ? 'Uploading…' : 'Upload'}
        </Button>
      </form>

      {upload.isError && (
        <div role="alert" className={styles.error}>
          {(upload.error as Error).message}
        </div>
      )}

      {job && (
        <div className={styles.job}>
          <h2>Job {job.id}</h2>
          <ul>
            <li>File ID: <code>{job.fileId}</code></li>
            <li>Status: <strong>{job.status}</strong></li>
            <li>Format: {job.format}</li>
            <li>Uploaded: {job.uploadedAt}</li>
            <li>Rows: {job.successRows ?? '—'} / {job.totalRows ?? '—'}  (failed: {job.failedRows ?? 0})</li>
          </ul>
          {!TERMINAL.has(job.status) && <Spinner />}
        </div>
      )}

      {recent.length > 0 && (
        <>
          <h2>Recent Uploads</h2>
          <table className={styles.recent}>
            <thead>
              <tr>
                <th>File</th>
                <th>Uploaded at</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.fileId}>
                  <td>{r.fileName}</td>
                  <td>{r.at}</td>
                  <td>
                    <button type="button" onClick={() => setTrackingId(r.fileId)}>
                      Check status
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
