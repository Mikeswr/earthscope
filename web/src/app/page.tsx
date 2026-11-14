const dashboardUrl = "https://earthscope.streamlit.app/";

const locations = ["Accra", "Kumasi", "Tamale", "Wa", "Takoradi"];

const capabilities = [
  {
    number: "01",
    title: "Long-term climate signals",
    description: "Explore monthly NASA POWER records, anomalies and statistically tested trends across selected locations in Ghana."
  },
  {
    number: "02",
    title: "Spatial exploration",
    description: "Move from a national overview to location-level evidence, with maps that make the geography of change easier to understand."
  },
  {
    number: "03",
    title: "Future outlook",
    description: "Compare forecasting approaches and inspect projected conditions alongside uncertainty, not just a single predicted line."
  }
];

export default function Home() {
  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="/" aria-label="EarthScope home">
          <span className="brand-mark"><span /></span>
          <span>earth<span className="brand-light">scope</span></span>
        </a>
        <div className="nav-links">
          <a href="#platform">Platform</a>
          <a href="#method">Our approach</a>
          <a className="nav-cta" href={dashboardUrl} target="_blank" rel="noreferrer">Open dashboard <span>↗</span></a>
        </div>
      </nav>

      <section className="hero shell">
        <div className="hero-copy">
          <div className="eyebrow"><span className="pulse" /> ENVIRONMENTAL INTELLIGENCE FOR GHANA</div>
          <h1>See the signal.<br /><em>Understand</em> the change.</h1>
          <p className="hero-lede">EarthScope turns environmental data into clear evidence. Explore where conditions are changing, how strong the signal is, and what the data may suggest about the future.</p>
          <div className="hero-actions">
            <a className="button button-primary" href={dashboardUrl} target="_blank" rel="noreferrer">Explore the dashboard <span>↗</span></a>
            <a className="text-link" href="#platform">Discover the platform <span>↓</span></a>
          </div>
          <div className="hero-footnote"><span className="dot" /> Built around transparent data and reproducible methods</div>
        </div>
        <div className="hero-visual" aria-label="Abstract visualization of environmental data trends">
          <div className="visual-top"><span>EARTH SYSTEM / GHANA</span><span>01 — 05</span></div>
          <div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" />
          <div className="globe">
            <div className="globe-grid" />
            <div className="land land-one" /><div className="land land-two" /><div className="land land-three" />
            <div className="globe-glow" />
          </div>
          <div className="data-tag tag-a"><span className="tag-dot" /> CLIMATE SIGNALS <b>1981–2025</b></div>
          <div className="data-tag tag-b"><span className="tag-dot teal" /> SPATIAL EVIDENCE <b>GHANA</b></div>
          <div className="visual-bottom"><span>OBSERVE</span><span>ANALYSE</span><span>INTERPRET</span></div>
        </div>
      </section>

      <section className="ticker" aria-label="Study locations">
        <div className="ticker-inner shell">
          <span className="ticker-label">STUDY LOCATIONS</span>
          {locations.map((location) => <span className="location" key={location}><i />{location}</span>)}
          <span className="ticker-note">GHANA, WEST AFRICA</span>
        </div>
      </section>

      <section className="platform shell" id="platform">
        <div className="section-heading">
          <div><div className="eyebrow dark">THE EARTHSCOPE PLATFORM</div><h2>Environmental change,<br /><em>made understandable.</em></h2></div>
          <p>From raw observations to meaningful evidence, EarthScope brings climate analysis, spatial context and forecasting into one connected experience.</p>
        </div>
        <div className="capability-grid">
          {capabilities.map((item) => (
            <article className="capability" key={item.number}>
              <div className="cap-number">{item.number}</div>
              <div className="cap-icon">{item.number === "01" ? "↗" : item.number === "02" ? "⌖" : "⌁"}</div>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="signal-section" id="method">
        <div className="signal-inner shell">
          <div className="signal-copy">
            <div className="eyebrow"><span className="pulse" /> A FEATURED RESEARCH SIGNAL</div>
            <h2>What is happening<br />to surface solar energy?</h2>
            <p>In the NASA POWER monthly record for the Accra grid point, EarthScope's documented analysis identified a statistically significant declining trend in estimated all-sky surface shortwave solar energy from 1984 to 2025.</p>
            <a className="text-link light-link" href={dashboardUrl} target="_blank" rel="noreferrer">Explore the evidence <span>↗</span></a>
          </div>
          <div className="signal-stat">
            <div className="stat-label">ESTIMATED CHANGE PER DECADE</div>
            <div className="stat-value">−0.0514</div>
            <div className="stat-unit">kWh/m²/day</div>
            <div className="stat-rule" />
            <div className="stat-meta"><span>1984–2025</span><span>Accra grid point</span></div>
            <div className="stat-caveat">A gridded estimate, not a direct measurement of solar-panel output. The signal requires independent validation against ground-based radiation observations.</div>
          </div>
        </div>
      </section>

      <section className="method-strip shell">
        <div><span className="method-index">01 / DATA</span><h3>NASA POWER</h3><p>Monthly gridded climate and solar radiation estimates.</p></div>
        <div><span className="method-index">02 / ANALYSIS</span><h3>Statistical evidence</h3><p>Mann-Kendall testing, Sen's slope and quality control.</p></div>
        <div><span className="method-index">03 / INTERPRETATION</span><h3>Context matters</h3><p>Uncertainty, limitations and evidence are made visible.</p></div>
      </section>

      <section className="closing shell">
        <div><div className="eyebrow dark">START EXPLORING</div><h2>Better questions begin<br />with <em>better evidence.</em></h2></div>
        <a className="button button-dark" href={dashboardUrl} target="_blank" rel="noreferrer">Enter EarthScope <span>↗</span></a>
      </section>

      <footer className="footer">
        <div className="shell footer-inner"><a className="brand footer-brand" href="/"><span className="brand-mark"><span /></span><span>earth<span className="brand-light">scope</span></span></a><span>Environmental intelligence for a changing world.</span><span>© {new Date().getFullYear()} EarthScope</span></div>
      </footer>
    </main>
  );
}
