import { useEffect, useState } from 'react';
import { Brand } from './Brand.jsx';

/** Appears after the hero leaves the viewport, and hides again when the hero returns. */
export default function Navbar({ onNavigate }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const hero = document.getElementById('home');
    if (!hero) return;
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(!entry.isIntersecting);
      if (entry.isIntersecting) setMobileOpen(false);
    }, { threshold: 0.02 });
    observer.observe(hero);
    return () => observer.disconnect();
  }, []);

  const navigate = (id) => {
    setMobileOpen(false);
    onNavigate(id);
  };

  return (
    <header className={`site-header floating-header ${visible ? 'is-visible' : ''}`} aria-hidden={!visible}>
      <nav className="navbar navbar-expand-lg container site-nav" aria-label="Main navigation">
        <Brand tabIndex={visible ? 0 : -1} />
        <button className="navbar-toggler" type="button" aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileOpen} onClick={() => setMobileOpen((open) => !open)} tabIndex={visible ? 0 : -1}>
          <i className={`bi ${mobileOpen ? 'bi-x-lg' : 'bi-list'}`} />
        </button>
        <div className={`nav-menu ${mobileOpen ? 'nav-menu-open' : ''}`}>
          <div className="nav-links">
            <a href="#home" tabIndex={visible ? 0 : -1} onClick={() => navigate('home')}>Home</a>
            <a href="#browse" tabIndex={visible ? 0 : -1} onClick={() => navigate('browse')}>Browse items</a>
            <a href="#how-it-works" tabIndex={visible ? 0 : -1} onClick={() => navigate('how-it-works')}>How it works</a>
            <a href="#report" tabIndex={visible ? 0 : -1} onClick={() => navigate('report')}>Report an item</a>
          </div>
          <button className="btn btn-brand nav-cta" tabIndex={visible ? 0 : -1} onClick={() => navigate('report')}><i className="bi bi-plus-lg me-2" />Report an item</button>
        </div>
      </nav>
    </header>
  );
}
