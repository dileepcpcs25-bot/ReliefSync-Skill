import { MAX_PRIORITY_SCORE, STATUS_RULE_TEXT, fmt } from '../constants'
import { useState } from 'react'
import { api } from '../services/api'
import { useQuery } from '../hooks/useQuery'
import { Badge, Card, EmptyState, Meter, PageHeader, QueryBoundary } from '../components/ui'

const METER_TONE = { Critical: 'red', High: 'amber', Medium: 'blue', Low: 'green' }

export default function SmartPriority() {
  const query = useQuery('/api/intelligence/priority')
  const [reports, setReports] = useState({})
  const [loadingId, setLoadingId] = useState(null)
  async function explain(id) { setLoadingId(id); try { const r = await api.get(`/api/intelligence/explain/${id}`); setReports((old) => ({ ...old, [id]: r })) } catch (e) { setReports((old) => ({ ...old, [id]: { error: e.message } })) } finally { setLoadingId(null) } }
  return (
    <>
      <PageHeader
        title="Smart priority ranking"
        subtitle="Open incidents ranked by a transparent score: severity + population affected, weighted by status."
        actions={<button type="button" className="btn" onClick={query.reload} disabled={query.loading}>Recalculate</button>}
      />
      <QueryBoundary query={query}>
        {(res) => (
          <>
            <p className="status-rule"><strong>{res.status_rule ?? STATUS_RULE_TEXT}</strong> Resolved records are kept for history but never ranked.</p>
            {res.items.length === 0 ? (
              <Card><EmptyState title="Nothing to rank">There are no active or monitoring disasters.</EmptyState></Card>
            ) : (
              <div className="grid">
                {res.items.map((p) => (
                  <Card key={p.disaster.id}>
                    <div className="rank-card">
                      <div className="rank-no" aria-label={`Rank ${p.rank}`}>#{p.rank}</div>
                      <div>
                        <strong>{p.disaster.disaster_type} - {p.disaster.location}</strong>{' '}
                        <Badge>{p.disaster.status}</Badge>
                        <Meter value={p.score} max={MAX_PRIORITY_SCORE} tone={METER_TONE[p.level]} label={`Priority score ${p.score} of ${MAX_PRIORITY_SCORE}`} />
                        <p className="muted">{p.explanation}</p>
                        <p className="sub">{fmt(p.disaster.people_affected)} people affected · severity {p.disaster.severity}</p>
                        <button className="btn btn-sm" type="button" onClick={() => explain(p.disaster.id)} disabled={loadingId === p.disaster.id}>{loadingId === p.disaster.id ? 'Explaining…' : 'Explain report'}</button>
                        {reports[p.disaster.id] && <div className="subpanel" role="status"><strong>{reports[p.disaster.id].provider || 'Report explanation'}</strong><p>{reports[p.disaster.id].explanation || reports[p.disaster.id].error}</p><small className="muted">Explanation of recorded factors; review source data and use professional judgement.</small></div>}
                        <details className="factors">
                          <summary>How this score is calculated</summary>
                          <p className="muted"><span className="tag-estimate">{p.label}</span> {p.method}</p>
                          <table>
                            <thead><tr><th>Factor</th><th>Input</th><th className="num">Points</th><th>Basis of the input</th></tr></thead>
                            <tbody>
                              {p.factors.map((f) => <tr key={f.name}><td>{f.name}</td><td>{f.input}</td><td className="num">{f.points}</td><td>{f.basis}</td></tr>)}
                            </tbody>
                          </table>
                          <p className="sub">Not a prediction: the score only orders incidents using the figures people entered.</p>
                        </details>
                      </div>
                      <div className="rank-score"><strong>{p.score}</strong><Badge>{p.level}</Badge></div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}
      </QueryBoundary>
    </>
  )
}
