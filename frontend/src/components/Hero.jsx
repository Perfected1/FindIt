import { useEffect, useState } from 'react';

const slides = [
  {
    eyebrow: 'A little help can go a long way',
    title: <>Lost something?<br /><span>Let’s help you find it.</span></>,
    description: 'FindIt connects people who have found missing belongings with the people searching for them. Browse reported items or share information about something you’ve found.',
    icon: 'bi-shield-check',
    visualTitle: 'Found item, safely reported',
    visualDescription: 'Every detail helps bring it home',
    status: 'Ready for review',
    image: 'hero-photo-keys',
    footnote: 'One community. One simple way to reunite people with their belongings.'
  },
  {
    eyebrow: 'Help someone find their way back to it',
    title: <>Found something?<br /><span>Help it get home.</span></>,
    description: 'Share what you found and where you found it. FindIt makes it easier for the right person to recognize their belongings while keeping your contact details private.',
    icon: 'bi-box-seam',
    visualTitle: 'A thoughtful found-item report',
    visualDescription: 'A few details can make a difference',
    status: 'Simple to report',
    image: 'hero-photo-wallet',
    footnote: 'No account needed. Just share the details that help.'
  },
  {
    eyebrow: 'A safer way to reconnect',
    title: <>Recognize it?<br /><span>Make a private claim.</span></>,
    description: 'Found something that looks familiar? Submit identifying details privately so the person who reported it can review your claim before confirming a match.',
    icon: 'bi-person-check',
    visualTitle: 'Claims reviewed with care',
    visualDescription: 'Distinctive details stay private',
    status: 'Privacy first',
    image: 'hero-photo-bag',
    footnote: 'Public listings stay simple. Personal details stay protected.'
  }
];

export default function Hero({ onNavigate }) {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const slide = slides[active];

  useEffect(() => {
    if (paused || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    const timer = window.setInterval(() => setActive(current => (current + 1) % slides.length), 6500);
    return () => window.clearInterval(timer);
  }, [paused]);

  const changeSlide = index => setActive((index + slides.length) % slides.length);

  return (
    <section id="home" className="hero-section" aria-roledescription="carousel" aria-label="Discover how FindIt works" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="container hero-grid">
        <div className="hero-copy" aria-live="polite" aria-atomic="true">
          <div className="trust-chip"><i className={`bi ${slide.icon}`} /> {slide.eyebrow}</div>
          <h1 key={`title-${active}`} className="hero-slide-copy">{slide.title}</h1>
          <p key={`description-${active}`} className="hero-description hero-slide-copy">{slide.description}</p>
          <div className="hero-actions">
            <button className="btn btn-brand btn-lg" onClick={() => onNavigate('browse')}><i className="bi bi-search me-2" />Browse found items</button>
            <button className="btn btn-outline-brand btn-lg" onClick={() => onNavigate('report')}><i className="bi bi-plus-circle me-2" />Report an item</button>
          </div>
          <div className="hero-footnote"><span className="footnote-icon"><i className="bi bi-people" /></span><span>{slide.footnote}</span></div>
          <div className="hero-carousel-controls" aria-label="Hero carousel controls">
            <div className="hero-carousel-dots">
              {slides.map((item, index) => <button key={item.eyebrow} className={`hero-carousel-dot ${active === index ? 'active' : ''}`} aria-label={`Show slide ${index + 1}: ${item.eyebrow}`} aria-current={active === index ? 'true' : undefined} onClick={() => changeSlide(index)} />)}
            </div>
            <span className="hero-carousel-count">0{active + 1} <span>/ 0{slides.length}</span></span>
            <button className="hero-carousel-arrow" onClick={() => changeSlide(active - 1)} aria-label="Previous slide"><i className="bi bi-arrow-left" /></button>
            <button className="hero-carousel-arrow" onClick={() => changeSlide(active + 1)} aria-label="Next slide"><i className="bi bi-arrow-right" /></button>
          </div>
        </div>
        <div className="hero-visual-wrap">
          <div className={`hero-image ${slide.image}`} role="img" aria-label="Personal belongings arranged on a neutral surface">
            <div className="photo-tag"><span className="tag-icon"><i className="bi bi-check2-circle" /></span><span><strong>{slide.visualTitle}</strong><small>{slide.visualDescription}</small></span><span className="tag-status">{slide.status}</span></div>
          </div>
          <div className="hero-visual-note"><span className="note-dot" /> Thoughtful reporting. Safer reunions.</div>
        </div>
      </div>
    </section>
  );
}
