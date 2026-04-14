import { useQuery } from '@tanstack/react-query';
import { enrollmentTimeline } from '../../api/bff';
import { Spinner } from '../../components/Spinner';
import styles from './Detail.module.css';

interface Props {
  memberId: string;
  onClose: () => void;
}

export function MemberDetail({ memberId, onClose }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['timeline', memberId],
    queryFn: () => enrollmentTimeline(memberId),
  });

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className={styles.drawer} role="dialog" aria-label="Member detail">
        <header className={styles.header}>
          <h2>Member Detail</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <section className={styles.body}>
          {isLoading && <Spinner />}
          {error && <div role="alert">{(error as Error).message}</div>}
          {data && (
            <>
              <h3>Enrollment Timeline (bitemporal)</h3>
              <table className={styles.timeline}>
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Status</th>
                    <th>Valid From</th>
                    <th>Valid To</th>
                    <th>Txn From</th>
                    <th>Txn To</th>
                    <th>In-Force</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((s) => (
                    <tr key={s.id} className={s.isInForce ? styles.inForce : styles.history}>
                      <td>{s.planName ?? s.planId.slice(0, 8)}</td>
                      <td>{s.status}</td>
                      <td>{s.validFrom}</td>
                      <td>{s.validTo}</td>
                      <td>{s.txnFrom}</td>
                      <td>{s.txnTo}</td>
                      <td>{s.isInForce ? '●' : '—'}</td>
                      <td className={styles.src}>{s.sourceSegmentRef ?? ''}</td>
                    </tr>
                  ))}
                  {data.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ textAlign: 'center', color: '#888' }}>
                        No enrollments
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          )}
        </section>
      </aside>
    </div>
  );
}
