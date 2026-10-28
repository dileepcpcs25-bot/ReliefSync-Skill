import { KINDS } from './mapConfig'

export default function Legend({ kinds = Object.keys(KINDS) }) {
  return (
    <ul className="map-legend" aria-label="Map legend">
      {kinds.map((k) => (
        <li key={k}>
          <span className={`pin pin-${KINDS[k].shape}`} style={{ '--pin': KINDS[k].color }} aria-hidden="true"><i>{KINDS[k].symbol}</i></span>
          {KINDS[k].label}
        </li>
      ))}
      <li><span className="pin pin-circle pin-approx" style={{ '--pin': '#667085' }} aria-hidden="true"><i>?</i></span>Dashed outline = approximate or inferred position</li>
    </ul>
  )
}
