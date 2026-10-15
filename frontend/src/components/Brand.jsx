export function Brand({ light = false, tabIndex }) {
  return <a className={`brand ${light ? 'brand-light' : ''}`} href="#home" aria-label="FindIt home" tabIndex={tabIndex}><span className="brand-mark"><i className="bi bi-geo-alt-fill" /></span><span>Find<span className="brand-it">It</span></span></a>;
}
