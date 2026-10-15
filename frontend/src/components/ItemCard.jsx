export default function ItemCard({ item, onDetails, onClaim }) {
  return (
    <article className="item-card h-100">
      <div className="item-card-top">
        <div className={`item-illustration ${item.tone}`}><i className={`bi ${item.icon}`} /></div>
        <span className="status-pill"><span /> Found item</span>
      </div>
      <div className="item-card-body">
        <div className="item-category">{item.category}</div>
        <h3>{item.name}</h3>
        <p className="item-description">{item.description}</p>
        <div className="item-meta">
          <span><i className="bi bi-geo-alt" />{item.location}</span>
          <span><i className="bi bi-clock" />{item.time}</span>
        </div>
        <div className="item-card-bottom">
          <span className="reference">{item.id}</span>
          <div className="d-flex gap-2">
            <button className="btn btn-sm btn-outline-brand" onClick={() => onDetails(item)}>View details</button>
            <button className="btn btn-sm btn-brand" onClick={() => onClaim(item)}>Claim</button>
          </div>
        </div>
      </div>
    </article>
  );
}
