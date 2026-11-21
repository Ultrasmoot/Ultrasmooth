/* Activity log */
// A timeline of event cards, 20 per page, with page buttons under the list. "All" asks the server for one page at a time
// a category tab collects the matching action types (the API filters by one action at a time) and pages through them here.
const ACT_PER_PAGE = 20;
const ACT_CATS = ['All', 'Bookings', 'Check-in / out', 'Maintenance', 'Resources', 'Other'];
const ACT_ICON = {
  alert:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5 5L4 17l3 3 5.7-5.7a4 4 0 0 0 5-5l-2.5 2.5-2.2-.5-.5-2.2z"/>',
  warn:   '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>',
  out:    '<path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9"/>',
  inn:    '<path d="M15 4h4v16h-4M8 8l-4 4 4 4M4 12h11"/>',
  ok:     '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  cal:    '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
  box:    '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5M12 12v9"/>',
  dot:    '<circle cx="12" cy="12" r="3"/>'
};
function actCategory(action){
  const a = String(action || '');
  if(a.startsWith('booking.')) return 'Bookings';
  if(a.startsWith('checkin.') || a.startsWith('checkout.')) return 'Check-in / out';
  if(a.startsWith('maintenance.')) return 'Maintenance';
  if(a.startsWith('resource.')) return 'Resources';
  return 'Other';
}
function actStyle(action){
  const a = String(action || ''), cat = actCategory(a);
  if(a === 'checkin.code_failed' || a === 'auth.login_failed' || a === 'booking.rejected' || a === 'appointment.declined') return {tone:'r', icon: ACT_ICON.alert};
  if(a === 'booking.approved') return {tone:'b', icon: ACT_ICON.ok};
  if(cat === 'Bookings') return {tone:'b', icon: ACT_ICON.cal};
  if(a.startsWith('checkout.')) return {tone:'g', icon: ACT_ICON.out};
  if(a.startsWith('checkin.')) return {tone:'g', icon: ACT_ICON.inn};
  if(a === 'maintenance.reported') return {tone:'a', icon: ACT_ICON.warn};
  if(cat === 'Maintenance') return {tone:'a', icon: ACT_ICON.wrench};
  if(cat === 'Resources') return {tone:'g', icon: ACT_ICON.box};
  return {tone:'b', icon: ACT_ICON.dot};
}
const ACT_DETAIL_LABEL = {'Bookings': 'Booking', 'Check-in / out': 'Resource', 'Maintenance': 'Issue', 'Resources': 'Resource', 'Other': 'Details'};

let actCat = 'All';
let actActions = [];
let actItems = [];
let actTotal = 0;
let actPage = 1, actPages = 1;
let actAll = [];
let actToken = 0, actLoading = false;

async function loadActivityMeta(){
  const {ok, data} = await apiAuthGet('/api/activity/meta');
  if(!ok) return;
  const user = document.getElementById('act-user'), action = document.getElementById('act-action');
  const keepU = user.value, keepA = action.value;
  actActions = data.actions;
  user.innerHTML = '<option value="">All users</option>' + data.users.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join('');
  action.innerHTML = '<option value="">All actions</option>' + data.actions.map(a => `<option value="${escapeHtml(a.value)}">${escapeHtml(a.label)}</option>`).join('');
  user.value = keepU; action.value = keepA;
}
function actParams(extra){
  const params = new URLSearchParams(extra);
  const f = {from: 'act-from', to: 'act-to', user: 'act-user'};
  for(const [k, id] of Object.entries(f)){
    const v = document.getElementById(id).value;
    if(v) params.set(k, v);
  }
  return params;
}
async function actFetch(extra){
  return apiAuthGet('/api/activity?' + actParams(extra).toString());
}

async function loadActivity(page = 1){
  const token = ++actToken;
  actLoading = true;
  actItems = []; actAll = []; actPage = page; actPages = 1; actTotal = 0;
  const box = document.getElementById('act-content');
  const picked = document.getElementById('act-action').value;
  if(actCat === 'All'){
    const extra = {page, per_page: ACT_PER_PAGE};
    if(picked) extra.action = picked;
    const {ok, data} = await actFetch(extra);
    if(token !== actToken) return true;
    actLoading = false;
    if(!ok){ box.innerHTML = `<p class="note">${escapeHtml(data.error || 'Could not load the activity log')}</p>`; return false; }
    actItems = data.items; actTotal = data.total; actPages = data.pages; actPage = data.page;
  }else{
    let kinds = actActions.filter(a => actCategory(a.value) === actCat).map(a => a.value);
    if(picked) kinds = kinds.filter(k => k === picked);
    const results = await Promise.all(kinds.map(async kind => {
      const out = [];
      for(let page = 1; page <= 10; page++){          // 10 x 100 per action type is far beyond a lab's log
        const {ok, data} = await actFetch({page, per_page: 100, action: kind});
        if(!ok) return {error: data.error};
        out.push(...data.items);
        if(page >= data.pages) break;
      }
      return {items: out};
    }));
    if(token !== actToken) return true;
    actLoading = false;
    const failed = results.find(r => r.error);
    if(failed){ box.innerHTML = `<p class="note">${escapeHtml(failed.error || 'Could not load the activity log')}</p>`; return false; }
    actAll = results.flatMap(r => r.items).sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : b.id - a.id));
    actTotal = actAll.length;
    actPages = Math.max(1, Math.ceil(actTotal / ACT_PER_PAGE));
    actItems = actAll.slice(0, ACT_PER_PAGE);
  }
  renderActivity();
  return true;
}
// A page button was pressed.
function goActivityPage(page){
  if(actLoading || page < 1 || page > actPages || page === actPage) return;
  if(actCat === 'All'){ loadActivity(page); }
  else{
    actPage = page;
    actItems = actAll.slice((page - 1) * ACT_PER_PAGE, page * ACT_PER_PAGE);
    renderActivity();
  }
  document.getElementById('view-activity').scrollIntoView({block: 'start'});
  window.scrollTo({top: 0});
}

function actPageList(cur, last){
  const keep = new Set([1, last, cur - 1, cur, cur + 1]);
  const out = []; let prev = 0;
  for(let p = 1; p <= last; p++){
    if(!keep.has(p)) continue;
    if(p - prev > 1) out.push('…');
    out.push(p); prev = p;
  }
  return out;
}
function renderActivityPager(){
  renderPager('act-end', 'Activity pages', actPage, actPages);
}
function actDay(d){ return d.toLocaleDateString('en-GB', {day: 'numeric', month: 'long', year: 'numeric'}); }
function actDayKey(d){ return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`; }
function actInitials(name){ return String(name || '?').split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase() || '?'; }
function renderActivity(){
  const tabs = document.getElementById('act-tabs');
  tabs.innerHTML = ACT_CATS.map(c => `<button class="act-tab" type="button" role="tab" aria-selected="${c === actCat}" data-cat="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join('')
    + `<span class="act-showing">${actItems.length ? `Showing ${(actPage - 1) * ACT_PER_PAGE + 1}–${(actPage - 1) * ACT_PER_PAGE + actItems.length} of ${actTotal}` : `${actTotal} records`}</span>`;
  const box = document.getElementById('act-content'), end = document.getElementById('act-end');
  if(!actItems.length){
    box.innerHTML = '<div class="act-empty">No activity records match these filters.</div>';
    end.innerHTML = '';
    return;
  }
  let html = '<div class="act-tl">', last = '';
  for(const a of actItems){
    const when = new Date(a.created_at);
    const key = actDayKey(when);
    if(key !== last){ html += `<div class="act-day"><span>${escapeHtml(actDay(when))}</span><i></i></div>`; last = key; }
    const cat = actCategory(a.action), st = actStyle(a.action);
    let detail = a.summary || '', badge = cat;
    const m = a.action === 'checkin.code_failed' && /^(.*) \((\d+ attempts? left)\)$/.exec(detail);
    if(m){ detail = m[1]; badge = m[2]; }
    html += `<div class="act-ev"><div class="act-node act-${st.tone}"><svg viewBox="0 0 24 24" aria-hidden="true">${st.icon}</svg></div>
      <div class="act-card act-${st.tone}">
        <div class="act-main">
          <div class="act-ttl">${escapeHtml(a.action_label)}<span class="act-badge">${escapeHtml(badge)}</span></div>
          <div class="act-time"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>${when.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit', hour12: true})}</div>
          <div class="act-det"><b>${ACT_DETAIL_LABEL[cat]}</b>${escapeHtml(detail)}</div>
        </div>
        <div class="act-who"><span class="act-av">${escapeHtml(actInitials(a.actor_name))}</span><span>${escapeHtml(a.actor_name)}</span></div>
      </div></div>`;
  }
  box.innerHTML = html + '</div>';
  renderActivityPager();
}
async function openActivity(){
  await loadActivityMeta();
  return loadActivity();
}
document.getElementById('act-tabs').addEventListener('click', e => {
  const b = e.target.closest('.act-tab');
  if(b && b.dataset.cat !== actCat){ actCat = b.dataset.cat; loadActivity(); }
});
['act-from', 'act-to', 'act-user', 'act-action'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => loadActivity());
});
document.getElementById('act-clear').addEventListener('click', () => {
  ['act-from', 'act-to', 'act-user', 'act-action'].forEach(id => { document.getElementById(id).value = ''; });
  actCat = 'All'; loadActivity();
});
// Same behaviour as the other Refresh buttons: spinner
setupRefreshButton('act-refresh', () => openActivity());
document.getElementById('act-end').addEventListener('click', e => {
  const b = e.target.closest('.act-pg');
  if(b && !b.disabled) goActivityPage(Number(b.dataset.page));
});
