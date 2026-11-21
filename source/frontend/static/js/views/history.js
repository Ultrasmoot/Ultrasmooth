/* Napakhet */
/* ---------------- Check-in / check-out history (admin only) ---------------- */
const HIST_PER_PAGE = 20;
let histPage = 1;
let histWired = false;

function histQuery(page){
  const params = new URLSearchParams({page: String(page), per_page: String(HIST_PER_PAGE)});
  const fields = {from: 'hist-from', to: 'hist-to', user: 'hist-user', resource: 'hist-resource'};
  Object.keys(fields).forEach(key => {
    const value = document.getElementById(fields[key]).value;
    if(value) params.set(key, value);
  });
  return params.toString();
}

function histFillSelect(id, items, allLabel){
  const select = document.getElementById(id);
  const chosen = select.value;
  select.innerHTML = `<option value="">${allLabel}</option>` +
    items.map(x => `<option value="${x.id}">${escapeHtml(x.name)}</option>`).join('');
  select.value = chosen;
}

function histDuration(row){
  if(!row.checked_out_at) return '';
  const minutes = Math.max(0, Math.round((new Date(row.checked_out_at) - new Date(row.checked_in_at)) / 60000));
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`;
}

function histClock(value){
  return new Date(value).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit', hour12: false});
}

// One card per check-in, grouped under the day of the check-in (same look as the Activity log).
function histEvent(row){
  const done = row.status === 'Done';
  const tone = done ? 'g' : 'a';
  const icon = done ? ACT_ICON.out : ACT_ICON.inn;
  const duration = histDuration(row);
  const times = `In ${histClock(row.checked_in_at)}` + (row.checked_out_at ? ` · Out ${histClock(row.checked_out_at)}` : ' · Not checked out yet')
    + (duration ? ` · ${duration}` : '');
  return `<div class="act-ev"><div class="act-node act-${tone}"><svg viewBox="0 0 24 24" aria-hidden="true">${icon}</svg></div>
    <div class="act-card act-${tone}">
      <div class="act-main">
        <div class="act-ttl">${escapeHtml(row.resource_name)}<span class="act-badge">${escapeHtml(row.status)}</span></div>
        <div class="act-time"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>${escapeHtml(times)}</div>
        <div class="act-det"><b>Booked</b>${escapeHtml(s5When(row.start_time))} – ${escapeHtml(s5Time(row.end_time))} · ${escapeHtml(row.resource_code)}</div>
      </div>
      <div class="act-who"><span class="act-av">${escapeHtml(actInitials(row.user_name))}</span><span>${escapeHtml(row.user_name)}</span></div>
    </div></div>`;
}

function renderHistoryPager(page, pages){
  renderPager('hist-end', 'History pages', page, pages);
}

function renderHistory(data){
  const box = document.getElementById('hist-content');
  if(!data.items.length){
    box.innerHTML = '<div class="act-empty">No check-ins match these filters.</div>';
    document.getElementById('hist-end').innerHTML = '';
    return;
  }
  const first = (data.page - 1) * data.per_page + 1;
  const last = first + data.items.length - 1;
  let html = `<div class="hist-meta">Showing ${first}–${last} of ${data.total}</div><div class="act-tl">`, lastDay = '';
  for(const row of data.items){
    const when = new Date(row.checked_in_at);
    const key = actDayKey(when);
    if(key !== lastDay){ html += `<div class="act-day"><span>${escapeHtml(actDay(when))}</span><i></i></div>`; lastDay = key; }
    html += histEvent(row);
  }
  box.innerHTML = html + '</div>';
  renderHistoryPager(data.page, data.pages);
}

async function loadHistory(page){
  const box = document.getElementById('hist-content');
  const {ok, data} = await apiAuthGet('/api/history?' + histQuery(page));
  if(!ok){
    box.innerHTML = `<p class="note">${escapeHtml(data.error || 'Could not load the history')}</p>`;
    return false;
  }
  histPage = data.page;
  renderHistory(data);
  return true;
}

async function openHistory(){
  if(!histWired){
    histWired = true;
    ['hist-from', 'hist-to', 'hist-user', 'hist-resource'].forEach(id =>
      document.getElementById(id).addEventListener('change', () => loadHistory(1)));
    document.getElementById('hist-end').addEventListener('click', (e) => {
      const b = e.target.closest('.act-pg');
      if(!b || b.disabled) return;
      loadHistory(Number(b.dataset.page)).then(() => window.scrollTo({top: 0}));
    });
    setupRefreshButton('hist-refresh', () => loadHistory(histPage));
    document.getElementById('hist-clear').addEventListener('click', () => {
      ['hist-from', 'hist-to', 'hist-user', 'hist-resource'].forEach(id => { document.getElementById(id).value = ''; });
      loadHistory(1);
    });
  }
  const meta = await apiAuthGet('/api/history/meta');
  if(meta.ok){
    histFillSelect('hist-user', meta.data.users, 'All users');
    histFillSelect('hist-resource', meta.data.resources, 'All resources');
  }
  loadHistory(1);
}
