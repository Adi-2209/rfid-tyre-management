import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const TOKEN_KEY = 'rfid_access_token';
const stations = [
  { id: 'TYRE_BUILDING', name: 'Tyre building', short: 'Building' },
  { id: 'CURING', name: 'Curing', short: 'Curing' },
  { id: 'QUALITY_INSPECTION', name: 'Quality inspection', short: 'Inspection' },
  { id: 'WAREHOUSE', name: 'Warehouse', short: 'Warehouse' },
];

async function request(path, options = {}) {
  const { body, skipAuth = false, ...fetchOptions } = options;
  const token = sessionStorage.getItem(TOKEN_KEY);
  const headers = { ...(fetchOptions.headers || {}) };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (!skipAuth && token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, {
    ...fetchOptions,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && !skipAuth) sessionStorage.removeItem(TOKEN_KEY);
    const detail = data.detail || `Request failed (${response.status})`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

function dateLabel(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function initials(name = '') {
  return name.trim().slice(0, 1).toUpperCase() || 'A';
}

function Brand({ compact = false }) {
  return (
    <div className={`brand ${compact ? 'brand-compact' : ''}`}>
      <div className="brand-mark"><span /><span /><span /><span /></div>
      <div><strong>TyreTrace</strong><small>RFID MANAGEMENT</small></div>
    </div>
  );
}

function AuthScreen({ setupRequired, onAuthenticated }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (setupRequired && password !== confirmPassword) {
      setError('The passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const endpoint = setupRequired ? '/auth/setup' : '/auth/login';
      const result = await request(endpoint, {
        method: 'POST',
        skipAuth: true,
        body: { username: username.trim(), password },
      });
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
      const user = await request('/auth/me');
      onAuthenticated(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-story">
        <Brand />
        <div className="auth-story-copy">
          <span className="eyebrow light-eyebrow">FACTORY FLOOR VISIBILITY</span>
          <h1>Every tyre.<br />Every checkpoint.</h1>
          <p>Follow each tyre from building to warehouse with one clear view of its journey and quality status.</p>
        </div>
        <div className="auth-flow" aria-label="Tyre journey">
          {stations.map((station, index) => (
            <div className="auth-flow-step" key={station.id}>
              <span className="flow-dot">{String(index + 1).padStart(2, '0')}</span>
              <span>{station.short}</span>
              {index < stations.length - 1 && <i />}
            </div>
          ))}
        </div>
        <div className="auth-story-foot">LIVE TRACEABILITY <span>•</span> QUALITY GATED</div>
      </section>
      <section className="auth-panel">
        <div className="auth-mobile-brand"><Brand /></div>
        <div className="auth-card">
          <div className="auth-card-icon">{setupRequired ? '✦' : '↗'}</div>
          <span className="eyebrow">{setupRequired ? 'FIRST-TIME SETUP' : 'WELCOME BACK'}</span>
          <h2>{setupRequired ? 'Create your admin account' : 'Sign in to TyreTrace'}</h2>
          <p className="auth-subtitle">{setupRequired ? 'Set up the account that manages your tyre tracking workspace.' : 'Use your workspace account to continue.'}</p>
          <form onSubmit={submit} className="auth-form">
            <label htmlFor="username">Username</label>
            <input id="username" autoComplete="username" minLength={3} maxLength={64} required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your username" />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete={setupRequired ? 'new-password' : 'current-password'} minLength={setupRequired ? 12 : 1} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder={setupRequired ? 'At least 12 characters' : 'Your password'} />
            {setupRequired && <>
              <label htmlFor="confirm-password">Confirm password</label>
              <input id="confirm-password" type="password" autoComplete="new-password" minLength={12} required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Enter password again" />
            </>}
            {error && <div className="form-error" role="alert">{error}</div>}
            <button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Please wait…' : setupRequired ? 'Create admin account' : 'Sign in'}<span>→</span></button>
          </form>
          {setupRequired && <p className="password-note">Use a unique password with at least 12 characters.</p>}
        </div>
        <div className="auth-panel-foot">TyreTrace RFID Management <span>·</span> Secure workspace access</div>
      </section>
    </main>
  );
}

function Sidebar({ active, onNavigate, onLogout, user }) {
  const navItems = [
    { id: 'dashboard', label: 'Overview', icon: '⌂', section: 'WORKSPACE' },
    { id: 'inventory', label: 'Tyre inventory', icon: '▦' },
    { id: 'register', label: 'Register tyre', icon: '＋' },
    { id: 'reads', label: 'Station reads', icon: '⌁', section: 'OPERATIONS' },
    { id: 'quality', label: 'Quality control', icon: '✓' },
  ];
  return (
    <aside className="sidebar">
      <Brand />
      <div className="sidebar-label">WORKSPACE</div>
      <nav>
        {navItems.map((item, index) => <div key={item.id}>
          {item.section && index > 0 && <div className="sidebar-label nav-section-label">{item.section}</div>}
          <button className={`nav-item ${active === item.id ? 'active' : ''}`} onClick={() => onNavigate(item.id)}>
            <span className="nav-icon">{item.icon}</span><span>{item.label}</span>
          </button>
        </div>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="floor-status"><span className="online-dot" /><div><b>Tracking system</b><small>Workspace connected</small></div></div>
        <div className="sidebar-user">
          <span className="avatar">{initials(user.username)}</span>
          <div className="user-name"><b>{user.username}</b><small>Administrator</small></div>
          <button className="icon-button logout-button" title="Sign out" onClick={onLogout}>↗</button>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ title, subtitle, user, onRefresh }) {
  return (
    <header className="topbar">
      <div><div className="breadcrumb">WORKSPACE <span>/</span> <b>{title.toUpperCase()}</b></div><h1>{title}</h1><p>{subtitle}</p></div>
      <div className="topbar-actions"><button className="button button-quiet refresh-button" onClick={onRefresh}><span>↻</span> Refresh</button><div className="topbar-divider" /><div className="topbar-user"><span className="avatar avatar-small">{initials(user.username)}</span><div><b>{user.username}</b><small>Administrator</small></div></div></div>
    </header>
  );
}

function StatusPill({ status }) {
  const value = status || 'Not scanned';
  const className = value === 'PASS' || value === 'WAREHOUSE' ? 'good' : value === 'FAIL' ? 'bad' : value === 'PENDING' || value === 'QUALITY_INSPECTION' ? 'warn' : 'neutral';
  const label = stations.find((station) => station.id === value)?.name || value;
  return <span className={`status-pill ${className}`}><i />{label}</span>;
}

function StatCard({ label, value, detail, icon, tone }) {
  return <article className="stat-card"><div className={`stat-icon ${tone}`}>{icon}</div><span className="stat-label">{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function InventoryTable({ items, onOpen, compact = false }) {
  if (!items.length) return <div className="empty-state"><span>▦</span><b>No tyres found</b><p>Register a tyre tag to start tracking its journey.</p></div>;
  return (
    <div className="table-scroll"><table className="data-table"><thead><tr><th>TYRE</th><th>RFID EPC</th><th>CURRENT STATION</th><th>QUALITY</th><th>LAST ACTIVITY</th>{!compact && <th />}</tr></thead>
      <tbody>{items.map((item) => <tr key={item.epc} onClick={() => onOpen(item.tyre_id)} className="click-row">
        <td><div className="tyre-cell"><span className="tyre-avatar">◉</span><div><b>{item.tyre_id}</b><small>{item.description || 'Tyre record'}</small></div></div></td>
        <td><code>{item.epc}</code></td>
        <td><span className="station-label"><span className="station-mark" />{stations.find((s) => s.id === item.current_station)?.name || 'Not scanned'}</span></td>
        <td><StatusPill status={item.quality_status} /></td>
        <td className="date-cell">{dateLabel(item.latest_read_at || item.latest_inspected_at)}</td>
        {!compact && <td><button className="row-action" aria-label={`Open ${item.tyre_id}`}>→</button></td>}
      </tr>)}</tbody></table></div>
  );
}

function LiveActivity({ observations, readers, apiConnected }) {
  return <section className="panel live-panel">
    <div className="panel-heading">
      <div><span className="eyebrow">LIVE CONNECTION</span><h3>Station activity</h3></div>
      <span className={`connection-badge ${apiConnected ? 'connected' : 'disconnected'}`}><i />{apiConnected ? 'API connected' : 'API unavailable'}</span>
    </div>
    <div className="live-grid">
      <div className="live-column">
        <h4>Recent scans <span>{observations.length}</span></h4>
        {!observations.length ? <p className="live-empty">No scans received yet. New ESP32 reads will appear here.</p> : observations.map((item) => (
          <div className="live-entry" key={item.observation_id}>
            <span className="live-entry-dot" />
            <div className="live-entry-copy"><b>{item.tyre_id}</b><small>{stations.find((station) => station.id === item.station_id)?.name || item.station_id} · {item.reader_id}</small></div>
            <time>{dateLabel(item.timestamp)}</time>
          </div>
        ))}
      </div>
      <div className="live-column">
        <h4>RFID readers <span>{readers.length}</span></h4>
        {!readers.length ? <p className="live-empty">No reader has checked in yet.</p> : readers.map((reader) => (
          <div className="live-entry" key={reader.reader_id}>
            <span className={`live-entry-dot ${reader.online ? '' : 'offline'}`} />
            <div className="live-entry-copy"><b>{reader.reader_id}</b><small>{stations.find((station) => station.id === reader.station_id)?.name || reader.station_id} · {reader.online ? 'Online' : 'Offline'}</small></div>
            <time>{reader.last_seen_at ? dateLabel(reader.last_seen_at) : 'Never seen'}</time>
          </div>
        ))}
      </div>
    </div>
    <p className="live-footnote">Scans refresh every 3 seconds. Readers send a heartbeat every 15 seconds and show offline after 45 seconds without one.</p>
  </section>;
}

function Dashboard({ items, onNavigate, onOpen, observations, readers, apiConnected }) {
  const total = items.length;
  const warehouse = items.filter((item) => item.current_station === 'WAREHOUSE').length;
  const atInspection = items.filter((item) => item.current_station === 'QUALITY_INSPECTION').length;
  const failed = items.filter((item) => item.quality_status === 'FAIL').length;
  const stationCounts = stations.map((station) => ({ ...station, count: items.filter((item) => item.current_station === station.id).length }));
  const recent = [...items].sort((a, b) => new Date(b.latest_read_at || b.latest_inspected_at || 0) - new Date(a.latest_read_at || a.latest_inspected_at || 0)).slice(0, 6);
  return <>
    <section className="welcome-banner"><div><span className="eyebrow light-eyebrow">PLANT SNAPSHOT</span><h2>Good to see you.</h2><p>Here’s what’s happening across your tyre checkpoints today.</p></div><div className="banner-graphic"><div className="banner-ring ring-one" /><div className="banner-ring ring-two" /><div className="banner-core">TT</div><span className="banner-tag tag-a">EPC TRACKING</span><span className="banner-tag tag-b">4 STATIONS</span></div></section>
    <section className="stats-grid">
      <StatCard label="REGISTERED TYRES" value={total} detail="Unique tyre tags in the system" icon="◉" tone="blue" />
      <StatCard label="AT INSPECTION" value={atInspection} detail="Awaiting quality disposition" icon="⌕" tone="amber" />
      <StatCard label="IN WAREHOUSE" value={warehouse} detail="Cleared for storage" icon="▤" tone="green" />
      <StatCard label="QUALITY FAILURES" value={failed} detail="Require review or rework" icon="!" tone="red" />
    </section>
    <section className="content-grid dashboard-grid">
      <article className="panel station-panel"><div className="panel-heading"><div><span className="eyebrow">PRODUCTION FLOW</span><h3>Tyres by checkpoint</h3></div><button className="text-link" onClick={() => onNavigate('inventory')}>View inventory <span>→</span></button></div>
        <div className="station-list">{stationCounts.map((station, index) => <div className="station-row" key={station.id}><div className="station-index">0{index + 1}</div><div className="station-row-main"><div className="station-row-title"><b>{station.name}</b><span>{station.count} {station.count === 1 ? 'tyre' : 'tyres'}</span></div><div className="progress-track"><span style={{ width: `${total ? Math.max(4, station.count / total * 100) : 0}%` }} /></div></div></div>)}</div>
        <div className="flow-foot"><span><i className="legend-dot" />Latest recorded checkpoint</span><span>{total} total</span></div>
      </article>
      <article className="panel quick-panel"><div className="panel-heading"><div><span className="eyebrow">QUICK ACTIONS</span><h3>Keep things moving</h3></div></div>
        <button className="quick-action" onClick={() => onNavigate('register')}><span className="quick-icon quick-blue">＋</span><span><b>Register a tyre</b><small>Link a new EPC tag</small></span><i>→</i></button>
        <button className="quick-action" onClick={() => onNavigate('reads')}><span className="quick-icon quick-violet">⌁</span><span><b>Record station read</b><small>Update a tyre’s checkpoint</small></span><i>→</i></button>
        <button className="quick-action" onClick={() => onNavigate('quality')}><span className="quick-icon quick-green">✓</span><span><b>Inspect a tyre</b><small>Save a quality decision</small></span><i>→</i></button>
      </article>
    </section>
    <section className="panel recent-panel"><div className="panel-heading"><div><span className="eyebrow">LATEST MOVEMENT</span><h3>Recent tyre activity</h3></div><button className="text-link" onClick={() => onNavigate('inventory')}>All tyres <span>→</span></button></div><InventoryTable items={recent} onOpen={onOpen} compact /></section>
    <LiveActivity observations={observations} readers={readers} apiConnected={apiConnected} />
  </>;
}

function InventoryPage({ items, onOpen, onNavigate }) {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return items;
    return items.filter((item) => `${item.tyre_id} ${item.epc} ${item.description || ''} ${item.current_station || ''}`.toLowerCase().includes(text));
  }, [items, query]);
  return <section className="panel inventory-panel"><div className="inventory-toolbar"><div><span className="eyebrow">TAG REGISTRY</span><h3>Tyre inventory <span className="count-badge">{items.length}</span></h3><p>Search tyre IDs, EPCs, or station names.</p></div><div className="inventory-tools"><label className="search-box"><span>⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search inventory" /></label><button className="button button-primary" onClick={() => onNavigate('register')}>＋ Add tyre</button></div></div><InventoryTable items={filtered} onOpen={onOpen} /></section>;
}

function RegisterPage({ onCreated }) {
  const [form, setForm] = useState({ tyre_id: '', epc: '', description: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { await request('/tags', { method: 'POST', body: form }); setForm({ tyre_id: '', epc: '', description: '' }); onCreated(`Tyre ${form.tyre_id} registered.`); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="form-layout"><section className="panel form-panel"><div className="panel-heading"><div><span className="eyebrow">TAG REGISTRATION</span><h3>Register a tyre</h3><p>Assign one RFID EPC to one tyre ID.</p></div><span className="form-heading-icon">＋</span></div><form className="app-form" onSubmit={submit}>
    <div className="form-row"><div><label>Tyre ID</label><input required value={form.tyre_id} onChange={(e) => setForm({ ...form, tyre_id: e.target.value })} placeholder="e.g. TYRE-2026-001" /></div><div><label>RFID EPC</label><input required value={form.epc} onChange={(e) => setForm({ ...form, epc: e.target.value })} placeholder="e.g. E2000017221101441890ABCD" /></div></div>
    <label>Description <span className="optional-label">OPTIONAL</span></label><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Tyre type, size, or production batch" />
    {error && <div className="form-error">{error}</div>}<div className="form-actions"><span className="helper-text">EPCs are normalized to uppercase.</span><button className="button button-primary" disabled={busy}>{busy ? 'Registering…' : 'Register tyre'} <span>→</span></button></div>
  </form></section><aside className="panel side-note"><span className="note-icon">◉</span><h3>One tag, one tyre</h3><p>Each EPC can belong to only one tyre, and each tyre can have only one RFID tag.</p><div className="note-divider" /><small>After registration, the tyre will appear in inventory and can be scanned at any checkpoint.</small></aside></div>;
}

function ReadsPage({ items, onSaved }) {
  const [form, setForm] = useState({ epc: '', station_id: stations[0].id, reader_id: 'READER-BUILD-01', antenna_id: '1', rssi_dbm: '-48' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selected = items.find((item) => item.epc === form.epc);
  function changeStation(station) {
    const suffix = station.toLowerCase().replaceAll('_', '-');
    setForm({ ...form, station_id: station, reader_id: `READER-${suffix}-01` });
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const saved = await request('/observations', { method: 'POST', body: { epc: form.epc, reader_id: form.reader_id, antenna_id: Number(form.antenna_id), station_id: form.station_id, rssi_dbm: Number(form.rssi_dbm), timestamp: new Date().toISOString() } });
      onSaved(`Read recorded at ${stations.find((s) => s.id === saved.station_id)?.name || saved.station_id}.`);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="form-layout"><section className="panel form-panel"><div className="panel-heading"><div><span className="eyebrow">CHECKPOINT EVENT</span><h3>Record a station read</h3><p>Use this form for simulation or manual reader checks.</p></div><span className="form-heading-icon read-icon">⌁</span></div><form className="app-form" onSubmit={submit}>
    <label>Tyre</label><select required value={form.epc} onChange={(e) => setForm({ ...form, epc: e.target.value })}><option value="">Choose a registered tyre</option>{items.map((item) => <option value={item.epc} key={item.epc}>{item.tyre_id} · {item.epc}</option>)}</select>
    {selected && <div className="selected-tyre"><span className="tyre-avatar">◉</span><div><b>{selected.tyre_id}</b><small>Last seen: {stations.find((s) => s.id === selected.current_station)?.name || 'Not scanned'}</small></div></div>}
    <div className="form-row"><div><label>Station</label><select value={form.station_id} onChange={(e) => changeStation(e.target.value)}>{stations.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></div><div><label>Reader ID</label><input required value={form.reader_id} onChange={(e) => setForm({ ...form, reader_id: e.target.value })} /></div></div>
    <div className="form-row"><div><label>Antenna ID</label><input type="number" min="1" required value={form.antenna_id} onChange={(e) => setForm({ ...form, antenna_id: e.target.value })} /></div><div><label>Signal strength (dBm)</label><input type="number" min="-150" max="50" step="0.1" required value={form.rssi_dbm} onChange={(e) => setForm({ ...form, rssi_dbm: e.target.value })} /></div></div>
    {error && <div className="form-error">{error}</div>}<div className="form-actions"><span className="helper-text">Timestamp is captured automatically.</span><button className="button button-primary" disabled={busy || !items.length}>{busy ? 'Saving…' : 'Save station read'} <span>→</span></button></div>
  </form></section><aside className="panel side-note"><span className="note-icon note-purple">⌁</span><h3>Reader assignment</h3><p>A reader ID is linked to the station where it first reports. Give each physical station its own reader ID.</p><div className="note-divider" /><small>A warehouse read is accepted only when the tyre’s latest quality inspection has passed.</small></aside></div>;
}

function QualityPage({ items, onSaved }) {
  const eligible = items.filter((item) => item.current_station === 'QUALITY_INSPECTION');
  const [tyreId, setTyreId] = useState('');
  const [passed, setPassed] = useState('pass');
  const [defect, setDefect] = useState('TREAD_WEAR');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await request(`/tyres/${encodeURIComponent(tyreId)}/inspections`, { method: 'POST', body: { passed: passed === 'pass', defect_code: passed === 'pass' ? null : defect, notes, inspector_id: 'WORKSPACE_ADMIN' } });
      setNotes(''); onSaved(`Inspection saved for ${tyreId}.`);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="form-layout"><section className="panel form-panel"><div className="panel-heading"><div><span className="eyebrow">QUALITY GATE</span><h3>Record inspection result</h3><p>Inspection is available after a tyre has been scanned at this station.</p></div><span className="form-heading-icon quality-icon">✓</span></div><form className="app-form" onSubmit={submit}>
    <label>Tyre awaiting inspection</label><select required value={tyreId} onChange={(e) => setTyreId(e.target.value)}><option value="">Choose a tyre at quality inspection</option>{eligible.map((item) => <option value={item.tyre_id} key={item.tyre_id}>{item.tyre_id} · {item.epc}</option>)}</select>
    {!eligible.length && <div className="inline-notice">No tyres are currently at Quality Inspection. Record a station read there first.</div>}
    <div className="form-row"><div><label>Result</label><select value={passed} onChange={(e) => setPassed(e.target.value)}><option value="pass">Pass</option><option value="fail">Fail</option></select></div>{passed === 'fail' && <div><label>Defect code</label><select value={defect} onChange={(e) => setDefect(e.target.value)}><option value="TREAD_WEAR">Tread wear</option><option value="SIDEWALL_MARK">Sidewall mark</option><option value="DIMENSION_CHECK">Dimension check</option><option value="OTHER">Other</option></select></div>}</div>
    <label>Inspection notes <span className="optional-label">OPTIONAL</span></label><textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Add inspection details" rows="3" />
    {error && <div className="form-error">{error}</div>}<div className="form-actions"><span className="helper-text">Failed tyres remain held at inspection.</span><button className="button button-primary" disabled={busy || !eligible.length}>{busy ? 'Saving…' : 'Save inspection'} <span>→</span></button></div>
  </form></section><aside className="panel side-note quality-note"><span className="note-icon note-green">✓</span><h3>Warehouse release</h3><p>Only a tyre whose latest inspection passed may be recorded at the warehouse checkpoint.</p><div className="note-divider" /><small>The database enforces this rule even if a read is sent outside the dashboard.</small></aside></div>;
}

function TyreDetail({ tyreId, onClose }) {
  const [record, setRecord] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { request(`/tyres/${encodeURIComponent(tyreId)}`).then(setRecord).catch((err) => setError(err.message)); }, [tyreId]);
  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}><section className="detail-modal"><div className="detail-header"><div><span className="eyebrow">TYRE RECORD</span><h2>{tyreId}</h2></div><button className="icon-button close-button" onClick={onClose} aria-label="Close">×</button></div>
    {error ? <div className="form-error">{error}</div> : !record ? <div className="loading-block">Loading tyre history…</div> : <>
      <div className="detail-summary"><div><small>RFID EPC</small><code>{record.tyre.epc}</code></div><div><small>CURRENT STATION</small><StatusPill status={record.current_station} /></div><div><small>QUALITY</small><StatusPill status={record.quality_status} /></div></div>
      <h3 className="timeline-heading">Checkpoint history</h3>
      <div className="timeline">{record.observations.length ? record.observations.map((obs) => <div className="timeline-item" key={obs.observation_id}><span className="timeline-dot" /><div><b>{stations.find((s) => s.id === obs.station_id)?.name || obs.station_id}</b><small>{dateLabel(obs.timestamp)} · {obs.reader_id} · {obs.rssi_dbm} dBm</small></div></div>) : <p className="muted">No station reads recorded.</p>}</div>
      {record.inspections.length > 0 && <><h3 className="timeline-heading">Inspections</h3><div className="timeline">{record.inspections.map((inspection) => <div className="timeline-item" key={inspection.inspection_id}><span className={`timeline-dot ${inspection.passed ? 'dot-good' : 'dot-bad'}`} /><div><b>{inspection.passed ? 'Passed' : `Failed · ${inspection.defect_code}`}</b><small>{dateLabel(inspection.inspected_at)}{inspection.notes ? ` · ${inspection.notes}` : ''}</small></div></div>)}</div></>}
    </>}
  </section></div>;
}

function AppShell({ user, onLogout }) {
  const [active, setActive] = useState('dashboard');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(true);
  const [toast, setToast] = useState('');
  const [detailId, setDetailId] = useState('');
  const [pageError, setPageError] = useState('');
  const [recentObservations, setRecentObservations] = useState([]);
  const [readers, setReaders] = useState([]);
  const [apiConnected, setApiConnected] = useState(false);
  const observationCursor = useRef(0);
  const liveRefreshInProgress = useRef(false);

  const refreshInventory = useCallback(async () => {
    setBusy(true); setPageError('');
    try { const response = await request('/tyres?limit=500'); setItems(response.items); setTotal(response.total); }
    catch (err) { setPageError(err.message); if (err.message.toLowerCase().includes('session')) onLogout(); }
    finally { setBusy(false); }
  }, [onLogout]);

  const refreshLiveActivity = useCallback(async (reset = false) => {
    if (liveRefreshInProgress.current) return;
    liveRefreshInProgress.current = true;
    try {
      const cursor = reset ? 0 : observationCursor.current;
      const [scanData, readerData] = await Promise.all([
        request(`/observations/recent?after_id=${cursor}&limit=25`),
        request('/readers/status'),
      ]);
      const scans = scanData.items.slice().reverse();
      observationCursor.current = scanData.cursor;
      setRecentObservations((current) => (reset ? scans : [...scans, ...current]).slice(0, 20));
      setReaders(readerData.readers);
      setApiConnected(true);
      if (scans.length) refreshInventory();
    } catch (err) {
      setApiConnected(false);
      if (err.message.toLowerCase().includes('session')) onLogout();
    } finally {
      liveRefreshInProgress.current = false;
    }
  }, [onLogout, refreshInventory]);

  useEffect(() => { refreshInventory(); }, [refreshInventory]);
  useEffect(() => {
    refreshLiveActivity(true);
    const timer = window.setInterval(() => refreshLiveActivity(), 3000);
    return () => window.clearInterval(timer);
  }, [refreshLiveActivity]);
  useEffect(() => { if (!toast) return undefined; const timer = setTimeout(() => setToast(''), 3500); return () => clearTimeout(timer); }, [toast]);

  const titleMap = { dashboard: ['Overview', 'A live view of tyre movement across your plant.'], inventory: ['Tyre inventory', 'Search and review every registered tyre.'], register: ['Register tyre', 'Add a tyre and link its RFID tag.'], reads: ['Station reads', 'Record and verify checkpoint observations.'], quality: ['Quality control', 'Review inspection results and release decisions.'] };
  const [title, subtitle] = titleMap[active] || titleMap.dashboard;
  function refreshButton() { refreshInventory(); }
  function openPage(page) { setPageError(''); setActive(page); }
  function actionDone(message) { setToast(message); refreshInventory(); setActive('inventory'); }

  return <div className="app-shell">
    <Sidebar active={active} onNavigate={openPage} onLogout={onLogout} user={user} />
    <main className="main-area"><Topbar title={title} subtitle={subtitle} user={user} onRefresh={refreshButton} />
      <div className="page-content">
        {toast && <div className="toast-message"><span>✓</span>{toast}<button onClick={() => setToast('')}>×</button></div>}
        {pageError && <div className="page-error"><b>Could not load dashboard data</b><span>{pageError}</span><button className="button button-quiet" onClick={refreshInventory}>Try again</button></div>}
        {busy && !items.length && !pageError ? <div className="loading-block">Loading your tyre workspace…</div> : <>
          {active === 'dashboard' && <Dashboard items={items} onNavigate={openPage} onOpen={setDetailId} observations={recentObservations} readers={readers} apiConnected={apiConnected} />}
          {active === 'inventory' && <InventoryPage items={items} onOpen={setDetailId} onNavigate={openPage} />}
          {active === 'register' && <RegisterPage onCreated={actionDone} />}
          {active === 'reads' && <ReadsPage items={items} onSaved={actionDone} />}
          {active === 'quality' && <QualityPage items={items} onSaved={actionDone} />}
        </>}
        <footer className="page-footer"><span>TYRETRACE RFID MANAGEMENT</span><span>{total} registered {total === 1 ? 'tyre' : 'tyres'}</span></footer>
      </div>
    </main>
    {detailId && <TyreDetail tyreId={detailId} onClose={() => setDetailId('')} />}
  </div>;
}

export default function App() {
  const [authMode, setAuthMode] = useState('loading');
  const [user, setUser] = useState(null);
  const logout = useCallback(async () => {
    try { if (sessionStorage.getItem(TOKEN_KEY)) await request('/auth/logout', { method: 'POST' }); } catch { /* clear the local session even if the API is offline */ }
    sessionStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setAuthMode('login');
  }, []);

  useEffect(() => {
    let mounted = true;
    async function initialize() {
      try {
        const status = await request('/auth/status', { skipAuth: true });
        if (!mounted) return;
        if (status.setup_required) { setAuthMode('setup'); return; }
        const token = sessionStorage.getItem(TOKEN_KEY);
        if (!token) { setAuthMode('login'); return; }
        const profile = await request('/auth/me');
        if (mounted) { setUser(profile); setAuthMode('ready'); }
      } catch {
        if (mounted) { sessionStorage.removeItem(TOKEN_KEY); setAuthMode('login'); }
      }
    }
    initialize();
    return () => { mounted = false; };
  }, []);

  if (authMode === 'loading') return <div className="boot-screen"><Brand /><span>Connecting to your workspace…</span></div>;
  if (authMode === 'setup' || authMode === 'login') return <AuthScreen setupRequired={authMode === 'setup'} onAuthenticated={(profile) => { setUser(profile); setAuthMode('ready'); }} />;
  return <AppShell user={user} onLogout={logout} />;
}
