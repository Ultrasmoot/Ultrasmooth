/* Jirat */
/* ---------------- Maintenance (US-6 / US-7) — Iteration 4 ---------------- */
// Everyone can report an issue; only an admin confirms / edits / resolves / dismisses.
// Non-admins only ever see (and the server only ever returns) their own reports.
const MT_BADGE = {'Reported':'b-blue', 'Open':'b-rust', 'In Progress':'b-amber', 'Resolved':'b-green', 'Dismissed':'b-faint'};
const MT_LABEL = {'Open':'Confirmed', 'Dismissed':'Rejected'};   // display only — the stored status value stays "Open"
const MT_HELP = {
  'Reported':'Waiting for an administrator to review this report.',
  'Open':'Confirmed — the resource is in Maintenance and cannot be booked.',
  'In Progress':'Being repaired — the resource is in Maintenance.',
  'Resolved':'Repair finished.',
  'Dismissed':'Rejected by an administrator — no repair needed.'
};
let mtGroup = 'reported';   // admin tab: reported | open | closed
let maintenanceCache = [];

function todayLocal(){
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function maintenanceBadge(status){
  return `<span class="badge ${MT_BADGE[status] || ''}">${escapeHtml(MT_LABEL[status] || status)}</span>`;
}

function maintenanceCard(m, isAdmin){
  const d = new Date(m.issue_date + 'T00:00:00');
  const resName = m.resource_name || `#${m.resource_id}`;
  const who = m.reporter_name || m.reporter_email || `User #${m.reported_by}`;
  const showEmail = m.reporter_email && m.reporter_email !== who;
  const isOpen = m.status === 'Open' || m.status === 'In Progress';
  const canAct = isAdmin && (m.status === 'Reported' || isOpen);
  const closed = m.closed_at
    ? `${m.status === 'Dismissed' ? 'Rejected' : 'Resolved'} ${new Date(m.closed_at).toLocaleString([], {dateStyle:'medium', timeStyle:'short'})}`
    : '';
  let actions = '';
  if(isAdmin && m.status === 'Reported'){
    actions = `<button class="req-btn decline" type="button" data-act="ask-dismiss">Reject</button>
               <button class="req-btn approve" type="button" data-act="ask-confirm">Confirm</button>`;
  } else if(isAdmin && isOpen){
    actions = `<button class="req-btn neutral" type="button" data-act="edit">Edit</button>
               <button class="req-btn approve" type="button" data-act="ask-resolve">Resolve</button>`;
  }
  return `
    <article class="req" data-id="${m.id}" data-status="${escapeHtml(m.status)}" data-name="${escapeHtml(resName)}">
      <div class="req-row">
        <div class="leaf" aria-hidden="true">
          <span class="leaf-mon">${d.toLocaleString('en-US', {month:'short'})}</span>
          <span class="leaf-day">${d.getDate()}</span>
          <span class="leaf-wd">${d.toLocaleString('en-US', {weekday:'short'})}</span>
        </div>
        <div class="req-body">
          <div class="req-title"><h3>${escapeHtml(resName)}</h3>${maintenanceBadge(m.status)}</div>
          <p class="req-purpose"><b>Issue</b>${escapeHtml(m.description)}</p>
          ${m.status === 'Dismissed' && m.dismiss_reason ? `<p class="req-purpose"><b>Reason</b>${escapeHtml(m.dismiss_reason)}</p>` : ''}
          <div class="req-foot">
            ${isAdmin ? `<div class="who"><span class="who-av">${escapeHtml(initialsOf(who))}</span><div><b>${escapeHtml(who)}</b>${showEmail ? `<span>${escapeHtml(m.reporter_email)}</span>` : ''}</div></div>` : ''}
            <span>${MT_HELP[m.status] || ''}</span>
            ${closed ? `<span>${closed}</span>` : ''}
          </div>
        </div>
        ${actions ? `<div class="req-actions">${actions}</div>` : ''}
      </div>
      ${canAct ? `<div class="req-confirm${m.status === 'Reported' ? ' with-reason' : ''}">
        <p class="req-confirm-text"></p>
        ${m.status === 'Reported' ? `<input class="req-reason" type="text" maxlength="255" placeholder="Reason for rejecting (required)" aria-label="Reason for rejecting (required)">` : ''}
        <div class="req-confirm-btns">
          <button class="req-btn back" type="button" data-act="cancel">Go back</button>
          <button class="req-btn go" type="button" data-act="go">Confirm</button>
        </div>
      </div>` : ''}
    </article>`;
}

function renderMaintenance(records, isAdmin){
  const list = document.getElementById('mt-list');
  const empty = document.getElementById('mt-empty');
  const note = document.getElementById('mt-note');
  const n = records.length;
  if(isAdmin){
    note.textContent = mtGroup === 'reported'
      ? (n === 0 ? 'All caught up — no reports are waiting for review.' : `${n} ${n === 1 ? 'report is' : 'reports are'} waiting for your review.`)
      : mtGroup === 'open'
        ? 'Confirmed issues — these resources are in Maintenance until every issue is resolved.'
        : 'Resolved or rejected issues, newest first.';
  } else {
    note.textContent = 'These are the issues you reported and their current status.';
  }
  if(!n){
    list.innerHTML = '';
    empty.textContent = !isAdmin ? 'You have not reported any issues yet.'
      : mtGroup === 'reported' ? 'No reports are waiting for review.'
      : mtGroup === 'open' ? 'Nothing is in maintenance right now.'
      : 'No resolved or rejected issues yet.';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  list.innerHTML = records.map(m => maintenanceCard(m, isAdmin)).join('');
}

async function loadMaintenance(silent = false){
  const isAdmin = currentRole === 'admin';
  const query = isAdmin ? `?group=${encodeURIComponent(mtGroup)}` : '';
  const {ok, data} = await apiAuthGet('/api/maintenance' + query);
  if(!ok){
    if(!silent) toast(data.error || 'Could not load maintenance issues');
    return false;
  }
  maintenanceCache = data.records;
  renderMaintenance(maintenanceCache, isAdmin);
  return true;
}

document.getElementById('mt-admin-tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-group]');
  if(!btn) return;
  mtGroup = btn.dataset.group;
  document.querySelectorAll('#mt-admin-tabs .filter-chip').forEach(b => b.classList.toggle('active', b.dataset.group === mtGroup));
  loadMaintenance();
});
setupRefreshButton('btn-refresh-maintenance', () => loadMaintenance());
document.getElementById('btn-report-issue').addEventListener('click', () => openMaintenanceModal());

// Confirm / Reject / Resolve: first click opens the inline confirm bar, second click sends it.
const MT_ASK = {
  confirm: {text: n => `Confirm the report for ${n}? The resource will move to Maintenance and cannot be booked until the issue is resolved.`, go: 'Yes, confirm', done: 'Report confirmed — resource is now in Maintenance'},
  dismiss: {text: n => `Reject the report for ${n}? The resource stays as it is, and the reporter will see your reason.`, go: 'Yes, reject', done: 'Report rejected'},
  resolve: {text: n => `Resolve the issue for ${n}? The resource returns to Available unless another issue is still open.`, go: 'Yes, resolve', done: 'Issue resolved'}
};
document.getElementById('mt-list').addEventListener('input', (e) => {
  if(e.target.classList.contains('req-reason')) e.target.classList.remove('invalid');
});
document.getElementById('mt-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if(!btn) return;
  const card = btn.closest('.req');
  const act = btn.dataset.act;
  const id = Number(card.dataset.id);

  if(act === 'edit'){ openMaintenanceEditModal(id); return; }
  if(act.startsWith('ask-')){
    const kind = act.slice(4);
    document.querySelectorAll('#mt-list .req.asking').forEach(c => c.classList.remove('asking', 'is-decline'));
    card.classList.add('asking');
    card.classList.toggle('is-decline', kind === 'dismiss');
    card.dataset.pending = kind;
    card.querySelector('.req-confirm-text').textContent = MT_ASK[kind].text(card.dataset.name);
    const go = card.querySelector('.req-btn.go');
    go.textContent = MT_ASK[kind].go;
    const reasonBox = card.querySelector('.req-reason');
    if(reasonBox){ reasonBox.value = ''; reasonBox.classList.remove('invalid'); }
    (kind === 'dismiss' && reasonBox ? reasonBox : go).focus();
    return;
  }
  if(act === 'cancel'){
    card.classList.remove('asking', 'is-decline');
    return;
  }
  if(act === 'go'){
    const kind = card.dataset.pending;
    // Rejecting needs a reason, which the reporter will see on their report.
    let body;
    if(kind === 'dismiss'){
      const reasonBox = card.querySelector('.req-reason');
      const reason = reasonBox ? reasonBox.value.trim() : '';
      if(!reason){
        reasonBox.classList.add('invalid');
        reasonBox.focus();
        toast('Please enter a reason for rejecting this report');
        return;
      }
      body = {reason};
    }
    btn.disabled = true;
    const {ok, data} = await apiAuthSend('POST', `/api/maintenance/${id}/${kind}`, body);
    if(!ok){
      // e.g. another admin already handled it — show why and refresh the list.
      toast(data.error || 'Could not update the issue');
      loadMaintenance(true);
      return;
    }
    toast(MT_ASK[kind].done);
    loadMaintenance();
  }
});

function maintenanceFormFields(m, isAdmin){
  const today = todayLocal();
  return `
      <div class="field"><label>Description</label><textarea id="mt-desc" required rows="3" maxlength="500" placeholder="What is wrong with it?" style="width:100%; font-family:inherit; font-size:13px; padding:8px; border:1px solid var(--line); border-radius:6px;">${escapeHtml(m?.description)}</textarea></div>
      <div class="field"><label>Issue date</label><input id="mt-date" type="date" required max="${today}" value="${escapeHtml(m?.issue_date || today)}"></div>
      `;
}

function showMaintenanceError(msg){
  document.getElementById('maintenance-form-error-text').textContent = msg;
  document.getElementById('maintenance-form-error').classList.add('show');
}

// US-6: report an issue. Admin: saved as Open and the resource moves to Maintenance.
// Anyone else: saved as Reported; the resource is untouched until an admin confirms.
async function openMaintenanceModal(preselectId){
  const isAdmin = currentRole === 'admin';
  let resources = resourceCache;
  const fresh = await apiAuthGet('/api/resources');
  if(fresh.ok) resources = fresh.data.resources;
  const opts = resources.length
    ? resources.map(r => `<option value="${r.id}">${escapeHtml(r.name)} (${escapeHtml(r.status)})</option>`).join('')
    : '<option value="" disabled selected>No resources found</option>';
  document.getElementById('modal-box').innerHTML = `
    <h3>Report an issue</h3>
    <div id="maintenance-form-error" class="login-error"><span>⚠</span><span id="maintenance-form-error-text"></span></div>
    <form id="maintenance-form">
      <div class="field"><label>Resource</label><select id="mt-resource" required>${opts}</select></div>
      <div id="mt-prior" class="mt-prior" hidden></div>
      ${maintenanceFormFields(null, isAdmin)}
      <p class="note" style="margin:0 0 10px;">${isAdmin
        ? 'Saving marks the resource as Maintenance and blocks new bookings.'
        : 'An administrator will review your report. The resource stays available for booking until it is confirmed.'}</p>
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:6px;">
        <button class="btn no" type="button" id="maintenance-form-cancel">Cancel</button>
        <button class="btn ok" type="submit">${isAdmin ? 'Save' : 'Submit report'}</button>
      </div>
    </form>`;
  document.getElementById('modal-backdrop').classList.add('open');
  if(preselectId){
    const sel = document.getElementById('mt-resource');
    if(sel) sel.value = String(preselectId);
  }
  // Admin + resource already in Maintenance: show the reports that put it there.
  // The first report is locked; a new one is labelled Second / Third / ... report.
  const MT_ORD = ['First','Second','Third','Fourth','Fifth','Sixth','Seventh','Eighth','Ninth','Tenth'];
  const mtOrdinal = n => n <= MT_ORD.length ? `${MT_ORD[n-1]} report` : `Report #${n}`;
  const priorBox = document.getElementById('mt-prior');
  const resSelect = document.getElementById('mt-resource');
  const descLabel = document.getElementById('mt-desc')?.closest('.field')?.querySelector('label');
  let priorToken = 0;
  const repHtml = (m, n) => `
    <div class="mt-rep">
      <div class="mt-rep-top"><b>${mtOrdinal(n)}</b><span class="mt-date">${escapeHtml(m.issue_date || '')}</span></div>
      <p>${escapeHtml(m.description)}</p>
      <small>${escapeHtml(m.reporter_name || m.reporter_email || ('User #' + m.reported_by))}</small>
    </div>`;
  async function refreshPrior(){
    const token = ++priorToken;
    const rid = Number(resSelect.value);
    const res = resources.find(r => r.id === rid);
    const reset = () => { priorBox.hidden = true; priorBox.innerHTML = ''; if(descLabel) descLabel.textContent = 'Description'; };
    if(!isAdmin || !res || res.status !== 'Maintenance'){ reset(); return; }
    const {ok, data} = await apiAuthGet(`/api/maintenance?group=open&resource_id=${rid}`);
    if(token !== priorToken) return;            // user switched resource while loading
    if(!ok || !data.records.length){ reset(); return; }
    const list = data.records.slice().sort((a, b) => a.id - b.id);   // oldest first
    priorBox.innerHTML = `<div class="mt-list">${list.map((m, i) => repHtml(m, i + 1)).join('')}</div>`
      + `<div class="mt-next" style="margin-top:12px;">New: ${mtOrdinal(list.length + 1)}</div>`;
    priorBox.hidden = false;
    if(descLabel) descLabel.textContent = `Description (${mtOrdinal(list.length + 1).toLowerCase()})`;
  }
  resSelect.addEventListener('change', refreshPrior);
  refreshPrior();

  document.getElementById('maintenance-form-cancel').addEventListener('click', closeModal);
  document.getElementById('maintenance-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('maintenance-form-error').classList.remove('show');
    const payload = {
      resource_id: Number(document.getElementById('mt-resource').value),
      description: document.getElementById('mt-desc').value.trim(),
      date: document.getElementById('mt-date').value
    };
    const submitBtn = e.currentTarget.querySelector('button[type="submit"]');
    const submitLabel = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving…';
    const {ok, data} = await apiAuthSend('POST', '/api/maintenance', payload);
    submitBtn.disabled = false;
    submitBtn.textContent = submitLabel;
    if(!ok){
      // SRS-6: missing/invalid data blocks saving with a validation message.
      showMaintenanceError(data.error || 'Could not save the issue.');
      return;
    }
    closeModal();
    toast(isAdmin ? 'Issue saved — resource is now in Maintenance' : 'Report sent — an administrator will review it');
    // Refresh whichever page the modal was opened from.
    if(document.body.dataset.view === 'resources') loadResources();
    if(document.body.dataset.view === 'maintenance') loadMaintenance();
  });
}

// US-7: admin edits an open record (the resource itself cannot be changed).
function openMaintenanceEditModal(id){
  const m = maintenanceCache.find(x => x.id === id);
  if(!m) return;
  document.getElementById('modal-box').innerHTML = `
    <h3>Edit issue</h3>
    <div id="maintenance-form-error" class="login-error"><span>⚠</span><span id="maintenance-form-error-text"></span></div>
    <form id="maintenance-form">
      <div class="field"><label>Resource</label><input value="${escapeHtml(m.resource_name || ('#' + m.resource_id))}" disabled></div>
      ${maintenanceFormFields(m, true)}
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:6px;">
        <button class="btn no" type="button" id="maintenance-form-cancel">Cancel</button>
        <button class="btn ok" type="submit">Save changes</button>
      </div>
    </form>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('maintenance-form-cancel').addEventListener('click', closeModal);
  document.getElementById('maintenance-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('maintenance-form-error').classList.remove('show');
    const payload = {
      description: document.getElementById('mt-desc').value.trim(),
      date: document.getElementById('mt-date').value
    };
    const {ok, data} = await apiAuthSend('PUT', `/api/maintenance/${id}`, payload);
    if(!ok){
      showMaintenanceError(data.error || 'Could not save changes.');
      return;
    }
    closeModal();
    toast('Issue updated');
    loadMaintenance();
  });
}
