/* Panisara */
/* ---------------- UI redesign: cards, Home, search, navbar ---------------- */
const ICON_PIN = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 14s4.5-4 4.5-7.5a4.5 4.5 0 0 0-9 0C3.5 10 8 14 8 14z" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="6.5" r="1.6" stroke="currentColor" stroke-width="1.3"/></svg>';
const ICON_CLOCK = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.3"/><path d="M8 4.8V8l2.2 1.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';
const ICON_NEXT = '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/><path d="M8.5 6.5L12 10l-3.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

// Stable colour tone (0-3) per category / status so the same category always looks the same.
function toneOf(s){
  let h = 0;
  for(const c of String(s ?? '')) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 4;
}

function resIcon(category){
  const c = String(category || '').toLowerCase();
  let path;
  if(/fabric|print|cut|build|mech/.test(c)){
    path = '<path d="M24 5 41 14.5v19L24 43 7 33.5v-19L24 5Z"/><path d="M7 14.5 24 24l17-9.5M24 24v19"/>';
  } else if(/electr|circuit|sensor|power/.test(c)){
    path = '<rect x="12" y="12" width="24" height="24" rx="3"/><rect x="19" y="19" width="10" height="10" rx="1.5"/><path d="M18 6v6M24 6v6M30 6v6M18 36v6M24 36v6M30 36v6M6 18h6M6 24h6M6 30h6M36 18h6M36 24h6M36 30h6"/>';
  } else if(/comput|vr|ar|server|gpu|network/.test(c)){
    path = '<rect x="6" y="9" width="36" height="25" rx="3"/><path d="M17 41h14M24 34v7"/>';
  } else {
    path = '<path d="M19 6h10M21 6v13L9 38a3 3 0 0 0 2.6 4.5h24.8A3 3 0 0 0 39 38L27 19V6"/><path d="M14 30h20"/>';
  }
  return `<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}

const STATUS_CLASS = {'Available':'st-available', 'In Use':'st-inuse', 'Maintenance':'st-maintenance'};

function resourceCard(r, opts = {}){
  const manage = !!opts.manage;
  const actions = [];
  if(manage){
    actions.push(`<button class="btn req-admin" type="button" data-action="edit" data-id="${r.id}">Edit</button>`);
    if(r.is_archived){
      actions.push(`<button class="btn ok req-admin" type="button" data-action="unarchive" data-id="${r.id}">Unarchive</button>`);
    }else{
      actions.push(`<button class="btn no req-admin" type="button" data-action="archive" data-id="${r.id}">Archive</button>`);
      if(r.status === 'Maintenance'){
        actions.push(`<button class="btn req-admin" type="button" data-action="restore" data-id="${r.id}">Return to Available</button>`);
      }
    }
  }
  if((r.status === 'Available' || r.status === 'In Use') && !r.is_archived){
    actions.push(`<button class="btn ok req-booker" type="button" data-action="book" data-id="${r.id}">Request</button>`);
  }
  // Iteration 4 (US-6): every role can report a problem with a resource.
  if(manage && !r.is_archived){
    actions.push(`<button class="btn" type="button" data-action="report" data-id="${r.id}">Report issue</button>`);
  }
  return `
    <article class="rcard" data-rid="${r.id}" data-tone="${toneOf(r.category)}">
      <div class="rcard-art">${resIcon(r.category)}<span class="rcard-status ${STATUS_CLASS[r.status] || ''}">${escapeHtml(r.status)}</span></div>
      <div class="rcard-code">${escapeHtml(r.resource_code)}${r.is_archived ? ' · Archived' : ''}</div>
      <h3 title="${escapeHtml(r.name)}">${escapeHtml(r.name)}</h3>
      <div class="pill">${ICON_PIN}<span>${escapeHtml(r.location)}</span></div>
      <div class="tags"><span class="tag">#${escapeHtml(r.category)}</span><span class="tag plain">${escapeHtml(r.type)}</span></div>
      <div class="rcard-actions">${actions.join('')}</div>
    </article>`;
}

function resourceHCard(r){
  return `
    <div class="hcard" data-rid="${r.id}" data-tone="${toneOf(r.category)}">
      <div class="rcard-art">${resIcon(r.category)}<span class="rcard-status ${STATUS_CLASS[r.status] || ''}">${escapeHtml(r.status)}</span></div>
      <div class="hcard-body">
        <div class="rcard-code">${escapeHtml(r.resource_code)}</div>
        <h3>${escapeHtml(r.name)}</h3>
        <div class="pill" style="width:auto; align-self:flex-start;">${ICON_PIN}<span>${escapeHtml(r.location)}</span></div>
        <div class="tags"><span class="tag">#${escapeHtml(r.category)}</span><span class="tag plain">${escapeHtml(r.type)}</span></div>
      </div>
    </div>`;
}

function requestCard(b, isAdmin){
  const tone = {Pending:2, Approved:0, Rejected:3}[b.status] ?? 1;
  const who = b.requester_name || b.requester_email || '';
  return `
    <article class="rcard qcard" data-tone="${tone}">
      <div class="qtop"><b>${escapeHtml(b.resource_name || ('#' + b.resource_id))}</b>${bookingBadge(b.status)}</div>
      <div class="pill">${ICON_CLOCK}<span>${fmtRange(b.start_time, b.end_time)}</span></div>
      <p class="qpurpose">${escapeHtml(b.purpose)}</p>
      ${isAdmin && who ? `<div class="note" style="margin:0;">Requested by ${escapeHtml(who)}</div>` : ''}
    </article>`;
}

/* ----- shared click handling for resource cards (Edit / Archive / Request) ----- */
function cardActionHandler(e){
  const btn = e.target.closest('button[data-action]');
  if(!btn){
    // Iteration 5: clicking the card itself (not one of its buttons) opens the detail page
    const card = e.target.closest('[data-rid]');
    if(card && !e.target.closest('button, a')) openResourceDetail(Number(card.dataset.rid));
    return;
  }
  const id = Number(btn.dataset.id);
  if(btn.dataset.action === 'edit') openResourceModal(id);
  if(btn.dataset.action === 'archive') archiveResource(id);
  if(btn.dataset.action === 'unarchive') unarchiveResource(id);
  if(btn.dataset.action === 'restore') openRestoreConfirm(id);
  if(btn.dataset.action === 'book') openBookingModal(id);
  if(btn.dataset.action === 'report') openMaintenanceModal(id);
}
['res-grid', 'home-available', 'home-results-grid'].forEach(id => {
  document.getElementById(id).addEventListener('click', cardActionHandler);
});

/* ----- navigation helpers ("View All" links, banners, logo) ----- */
function goView(key, filters = {}){
  if(key === 'resources'){
    document.getElementById('res-filter-category').value = filters.category || '';
    document.getElementById('res-filter-location').value = '';
    document.getElementById('res-filter-status').value = filters.status || '';
    document.getElementById('res-filter-availability').checked = false;
    document.getElementById('res-search').value = '';
  }
  const btn = document.querySelector(`.nav-item[data-view="${key}"]`);
  if(btn) btn.click();
}
document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-goto]');
  if(t) goView(t.dataset.goto, {category: t.dataset.category, status: t.dataset.status});
});
document.getElementById('brand-home').addEventListener('click', () => goView('home'));

// navbar gets a frosted background once the page is scrolled
window.addEventListener('scroll', () => {
  document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 10);
});

/* ----- Home data ----- */
function fillSelect(sel, firstLabel, values){
  const prev = sel.value;
  sel.innerHTML = `<option value="">${firstLabel}</option>` +
    values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
  sel.value = prev;
}

function renderHomeResources(list){
  const available = list.filter(r => r.status === 'Available');
  document.getElementById('home-available-count').textContent = available.length;
  document.getElementById('home-available').innerHTML = available.length
    ? available.slice(0, 8).map(r => resourceCard(r)).join('')
    : '<p class="note" style="margin:0;">No resources are available right now.</p>';

  // Category banners: the 3 biggest categories, each showing its newest resource.
  const groups = {};
  list.forEach(r => { (groups[r.category] = groups[r.category] || []).push(r); });
  const top = Object.entries(groups).sort((a, b) => b[1].length - a[1].length).slice(0, 3);
  document.getElementById('home-categories').innerHTML = top.length
    ? top.map(([cat, items]) => {
        const newest = items.reduce((a, b) => (b.id > a.id ? b : a));
        return `
          <div class="banner" data-tone="${toneOf(cat)}" data-goto="resources" data-category="${escapeHtml(cat)}" role="button" tabindex="0">
            <div class="banner-art">${resIcon(cat)}</div>
            <div class="banner-in">
              <div class="banner-top"><h3>${escapeHtml(cat)}</h3><span class="view-all">View All (${items.length}) ${ICON_NEXT}</span></div>
              ${resourceHCard(newest)}
            </div>
          </div>`;
      }).join('')
    : '<p class="note" style="margin:0;">No resource categories yet.</p>';

  fillSelect(document.getElementById('hf-category'), 'All categories', [...new Set(list.map(r => r.category))].sort());
  fillSelect(document.getElementById('hf-location'), 'All locations', [...new Set(list.map(r => r.location))].sort());
}

function renderHomeRequests(bookings, isAdmin){
  document.getElementById('home-requests-title').textContent = isAdmin ? 'Pending Requests' : 'My Requests';
  document.getElementById('home-requests-count').textContent = bookings.length;
  document.getElementById('home-requests').innerHTML = bookings.length
    ? bookings.slice(0, 8).map(b => requestCard(b, isAdmin)).join('')
    : `<p class="note" style="margin:0;">${isAdmin ? 'No requests are waiting for review.' : 'You have no requests yet.'}</p>`;
}

// Home: a student sees the appointments they asked for; a professor sees the requests sent to them.
// Administrators have no appointments, so the row is hidden for them.
function apptCard(a, isProfessor){
  const st = a.expired ? 'Expired' : a.status;
  const tone = {Pending:2, Accepted:0, Declined:3}[st] ?? 1;
  const who = isProfessor ? `from ${a.student_name}` : `with ${a.professor_name}`;
  return `
    <article class="rcard qcard" data-tone="${tone}">
      <div class="qtop"><b>${escapeHtml(a.topic)}</b>${s5Badge(st, APPT_BADGE[st])}</div>
      <div class="pill">${ICON_CLOCK}<span>${fmtRange(a.start_time, a.end_time)}</span></div>
      <p class="qpurpose">${escapeHtml(who)}</p>
      ${a.decision_reason ? `<div class="note" style="margin:0;">Reason: ${escapeHtml(a.decision_reason)}</div>` : ''}
    </article>`;
}

function renderHomeAppointments(list, isProfessor){
  document.getElementById('home-appts-sec').hidden = false;
  document.getElementById('home-appts-title').textContent = isProfessor ? 'Appointment Requests' : 'My Appointments';
  document.getElementById('home-appts-count').textContent = list.length;
  document.getElementById('home-appts').innerHTML = list.length
    ? list.slice(0, 8).map(a => apptCard(a, isProfessor)).join('')
    : `<p class="note" style="margin:0;">${isProfessor ? 'No appointment requests yet.' : 'You have not asked a professor for an appointment yet.'}</p>`;
}

// Home: admin sees the reports waiting for review; everyone else sees the issues they reported.
function issueCard(m, isAdmin){
  const tone = {'Reported':2, 'Open':1, 'In Progress':1, 'Resolved':0, 'Dismissed':3}[m.status] ?? 1;
  const who = m.reporter_name || m.reporter_email || '';
  const when = new Date(m.issue_date + 'T00:00:00').toLocaleDateString([], {dateStyle:'medium'});
  return `
    <article class="rcard qcard" data-tone="${tone}">
      <div class="qtop"><b>${escapeHtml(m.resource_name || ('#' + m.resource_id))}</b>${maintenanceBadge(m.status)}</div>
      <div class="pill">${ICON_CLOCK}<span>${escapeHtml(when)}</span></div>
      <p class="qpurpose">${escapeHtml(m.description)}</p>
      ${isAdmin && who ? `<div class="note" style="margin:0;">Reported by ${escapeHtml(who)}</div>` : ''}
    </article>`;
}

function renderHomeIssues(records, isAdmin){
  document.getElementById('home-issues-title').textContent = isAdmin ? 'Pending Report Issues' : 'My Reported Issues';
  document.getElementById('home-issues-count').textContent = records.length;
  document.getElementById('home-issues').innerHTML = records.length
    ? records.slice(0, 8).map(m => issueCard(m, isAdmin)).join('')
    : `<p class="note" style="margin:0;">${isAdmin ? 'No issue reports are waiting for review.' : 'You have not reported any issues yet.'}</p>`;
}

async function loadHome(){
  const isAdmin = currentRole === 'admin';
  const isProfessor = currentRole === 'professor';
  const apptUrl = isAdmin ? null : (isProfessor ? '/api/appointments/inbox' : '/api/appointments/mine');
  const [res, bk, mt, ap] = await Promise.all([
    apiAuthGet('/api/resources'),
    apiAuthGet(isAdmin ? '/api/bookings/pending' : '/api/bookings/mine'),
    apiAuthGet(isAdmin ? '/api/maintenance?group=reported' : '/api/maintenance'),
    apptUrl ? apiAuthGet(apptUrl) : Promise.resolve(null)
  ]);
  if(res.ok){
    resourceCache = res.data.resources;
    populateFilterOptions(resourceCache);
    renderHomeResources(resourceCache);
  }
  if(bk.ok) renderHomeRequests(bk.data.bookings, isAdmin);
  if(mt.ok) renderHomeIssues(mt.data.records, isAdmin);
  if(!apptUrl) document.getElementById('home-appts-sec').hidden = true;
  else if(ap && ap.ok) renderHomeAppointments(ap.data.appointments, isProfessor);
}

/* ----- Home search + filter card ----- */
const homeSearch = document.getElementById('home-search');
const homeFilterCard = document.getElementById('home-filter-card');
let homeSearchTimer = null;

async function runHomeSearch(){
  const q = homeSearch.value.trim();
  const category = document.getElementById('hf-category').value;
  const location = document.getElementById('hf-location').value;
  const status = document.getElementById('hf-status').value;
  const active = !!(q || category || location || status);

  document.getElementById('home-clear-inline').style.display = active ? '' : 'none';
  document.getElementById('home-results').style.display = active ? 'block' : 'none';
  document.getElementById('home-sections').style.display = active ? 'none' : 'block';
  if(!active) return;

  const params = new URLSearchParams();
  if(q) params.set('q', q);
  if(category) params.set('category', category);
  if(location) params.set('location', location);
  if(status) params.set('status', status);
  const {ok, data} = await apiAuthGet('/api/resources?' + params.toString());
  if(!ok){ toast('Could not search resources'); return; }
  document.getElementById('home-results-title').textContent = `Search results (${data.resources.length})`;
  document.getElementById('home-results-grid').innerHTML = data.resources.map(r => resourceCard(r)).join('');
  document.getElementById('home-results-empty').style.display = data.resources.length ? 'none' : 'block';
}

function clearHomeSearch(){
  homeSearch.value = '';
  ['hf-category', 'hf-location', 'hf-status'].forEach(id => { document.getElementById(id).value = ''; });
  homeFilterCard.classList.remove('open');
  runHomeSearch();
}

homeSearch.addEventListener('input', () => {
  clearTimeout(homeSearchTimer);
  homeSearchTimer = setTimeout(runHomeSearch, 250);
});
homeSearch.addEventListener('focus', () => homeFilterCard.classList.remove('open'));
['hf-category', 'hf-location', 'hf-status'].forEach(id => {
  document.getElementById(id).addEventListener('change', runHomeSearch);
});
document.getElementById('home-filter-toggle').addEventListener('click', (e) => {
  e.stopPropagation();
  homeFilterCard.classList.toggle('open');
});
homeFilterCard.addEventListener('click', (e) => e.stopPropagation());
document.getElementById('home-clear').addEventListener('click', clearHomeSearch);
document.getElementById('home-clear-inline').addEventListener('click', clearHomeSearch);
document.addEventListener('click', () => homeFilterCard.classList.remove('open'));


/* floating side menu: tap/click support for touch screens */
(function(){
  const nb = document.getElementById('navbar');
  document.getElementById('nav-handle').addEventListener('click', (e) => { e.stopPropagation(); nb.classList.toggle('open'); });
  nb.addEventListener('click', (e) => { if(e.target.closest('.nav-item')) nb.classList.remove('open'); });
  document.addEventListener('click', (e) => { if(!e.target.closest('.navbar-in')) nb.classList.remove('open'); });
})();
/* Jirat */
/* ---------------- Init + Napakhet + Panisara ---------------- */
applyRole('admin'); // default demo state; overridden below if a real session restores
restoreSession();
// Opening the emailed reset link (/?reset_token=...) jumps straight to
// the "set a new password" form instead of the login screen.
if(new URLSearchParams(window.location.search).get('reset_token')){
  showAuthView('reset-password');
}

// Opening the emailed verification link (/?verify_token=...): confirm it with the
// backend, drop the token from the address bar (single-use), and tell the user on the login screen.
(async function handleVerifyLink(){
  const token = new URLSearchParams(window.location.search).get('verify_token');
  if(!token) return;
  history.replaceState(null, '', window.location.pathname);
  showAuthView('login');
  try{
    const {ok, data} = await apiPost('/verify-email', {token});
    if(ok){
      showLoginNotice(data.message || 'Email verified. You can now log in.');
    } else {
      showLoginError(data.error || 'This verification link is invalid or has expired.');
      showResendLink();   // lets the user ask for a fresh link
    }
  } catch(err){
    showLoginError('Could not reach the server. Is the backend running?');
  }
})();
