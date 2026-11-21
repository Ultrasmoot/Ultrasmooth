/* ---------------- Requests (US-3/US-4/US-5) ---------------- */
function fmtRange(startIso, endIso){
  const opts = {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'};
  return `${new Date(startIso).toLocaleString([], opts)} – ${new Date(endIso).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
}

function bookingBadge(status){
  const map = {Pending:'b-amber', Approved:'b-green', Rejected:'b-rust', Cancelled:'b-faint'};
  return `<span class="badge ${map[status] || ''}">${status}</span>`;
}

let bookingFilter = 'All';

document.getElementById('booking-filters').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-filter]');
  if(!btn) return;
  bookingFilter = btn.dataset.filter;
  document.querySelectorAll('#booking-filters .filter-chip').forEach(b => {
    b.classList.toggle('active', b.dataset.filter === bookingFilter);
  });
  loadBookings();
});

let adminTab = 'pending';
document.getElementById('admin-bk-tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-tab]');
  if(!btn) return;
  adminTab = btn.dataset.tab;
  document.querySelectorAll('#admin-bk-tabs .filter-chip').forEach(b => b.classList.toggle('active', b.dataset.tab === adminTab));
  document.getElementById('admin-bk-note').textContent = adminTab === 'history'
    ? 'Requests already decided, newest first — with the time of the decision.'
    : 'Showing requests awaiting your review.';
  loadBookings();
});

async function loadBookings(silent = false){
  const isAdmin = currentRole === 'admin';
  const path = isAdmin ? (adminTab === 'history' ? '/api/bookings/history' : '/api/bookings/pending') : '/api/bookings/mine';
  const {ok, data} = await apiAuthGet(path);
  if(!ok){
    if(!silent) toast(data.error || 'Could not load requests');
    return false;
  }
  renderBookings(data.bookings, isAdmin);
  return true;
}

// SRS-4: status changes made by a Lab Manager/Administrator show up on their
// own — manual Refresh button plus a quiet background reload every 30 s while
// the Requests view is open (skipped when the tab is hidden or a form is open).
setupRefreshButton('btn-refresh-bookings', () => loadBookings());
setInterval(() => {
  const onRequests = document.getElementById('view-bookings').classList.contains('active');
  const modalOpen = document.getElementById('modal-backdrop').classList.contains('open');
  if(document.body.classList.contains('authed') && onRequests && !modalOpen && !document.hidden && !document.querySelector('#bk-list .req.asking')){
    loadBookings(true);
  }
}, 30000);

function fmtDuration(ms){
  const m = Math.max(0, Math.round(ms / 60000));
  if(m < 60) return `${m} min`;
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  const parts = [];
  if(d) parts.push(`${d} ${d > 1 ? 'days' : 'day'}`);
  if(h) parts.push(`${h} h`);
  if(mm && !d) parts.push(`${mm} min`);
  return parts.join(' ');
}

function initialsOf(name){
  return String(name || '?').split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase() || '?';
}

function bookingWhen(b){
  const s = new Date(b.start_time), e = new Date(b.end_time);
  const t = d => d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  const dt = d => d.toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
  return s.toDateString() === e.toDateString() ? `${t(s)} – ${t(e)}` : `${dt(s)} to ${dt(e)}`;
}

function bookingCard(b, isAdmin){
  const s = new Date(b.start_time), e = new Date(b.end_time);
  const resName = b.resource_name || `#${b.resource_id}`;
  const who = b.requester_name || b.requester_email || `User #${b.requester_id}`;
  const showEmail = b.requester_email && b.requester_email !== who;
  const decided = b.status === 'Cancelled' && b.cancelled_at
    ? `Cancelled ${new Date(b.cancelled_at).toLocaleString([], {dateStyle:'medium', timeStyle:'short'})}`
    : (b.decided_at ? `Decided ${new Date(b.decided_at).toLocaleString([], {dateStyle:'medium', timeStyle:'short'})}` : '');
  const canDecide = isAdmin && b.status === 'Pending';
  // The requester may withdraw a waiting request, or an approved booking that has not ended
  // (the server refuses it if they have already checked in).
  const canCancel = !isAdmin && (b.status === 'Pending' || (b.status === 'Approved' && e > new Date()));
  return `
    <article class="req" data-id="${b.id}" data-status="${escapeHtml(b.status)}" data-name="${escapeHtml(resName)}">
      <div class="req-row">
        <div class="leaf" aria-hidden="true">
          <span class="leaf-mon">${s.toLocaleString('en-US', {month:'short'})}</span>
          <span class="leaf-day">${s.getDate()}</span>
          <span class="leaf-wd">${s.toLocaleString('en-US', {weekday:'short'})}</span>
        </div>
        <div class="req-body">
          <div class="req-title"><h3>${escapeHtml(resName)}</h3>${bookingBadge(b.status)}</div>
          <div class="req-when">${ICON_CLOCK}<span>${bookingWhen(b)}</span><span class="dur">${fmtDuration(e - s)}</span></div>
          <p class="req-purpose"><b>Purpose</b>${escapeHtml(b.purpose)}</p>
          ${b.status === 'Rejected' && b.decision_reason ? `<p class="req-purpose"><b>Reason</b>${escapeHtml(b.decision_reason)}</p>` : ''}
          ${(isAdmin || decided) ? `<div class="req-foot">
            ${isAdmin ? `<div class="who"><span class="who-av">${escapeHtml(initialsOf(who))}</span><div><b>${escapeHtml(who)}</b>${showEmail ? `<span>${escapeHtml(b.requester_email)}</span>` : ''}</div></div>` : ''}
            ${decided ? `<span>${decided}</span>` : ''}
          </div>` : ''}
        </div>
        ${canCancel ? `<div class="req-actions"><button class="req-btn decline" type="button" data-act="ask-cancel">Cancel request</button></div>` : ''}
        ${canDecide ? `<div class="req-actions">
          <button class="req-btn decline" type="button" data-act="ask-reject">Reject</button>
          <button class="req-btn approve" type="button" data-act="ask-approve">Approve</button>
        </div>` : ''}
      </div>
      ${canDecide ? `<div class="req-confirm with-reason">
        <p class="req-confirm-text"></p>
        <input class="req-reason" type="text" maxlength="255" placeholder="Reason for rejecting (optional)" aria-label="Reason for rejecting (optional)">
        <div class="req-confirm-btns">
          <button class="req-btn back" type="button" data-act="cancel">Go back</button>
          <button class="req-btn go" type="button" data-act="confirm">Confirm</button>
        </div>
      </div>` : ''}
    </article>`;
}

function renderBookings(bookings, isAdmin){
  const list = document.getElementById('bk-list');
  const empty = document.getElementById('bk-empty');
  const filtered = isAdmin || bookingFilter === 'All'
    ? bookings
    : bookings.filter(b => b.status === bookingFilter);

  if(isAdmin){
    const n = filtered.length;
    document.getElementById('admin-bk-note').textContent = adminTab === 'history'
      ? 'Decided requests, newest first.'
      : (n === 0 ? 'All caught up — nothing is waiting for review.' : `${n} ${n === 1 ? 'request is' : 'requests are'} waiting for your review.`);
  }

  if(!filtered.length){
    list.innerHTML = '';
    empty.textContent = isAdmin
      ? (adminTab === 'history' ? 'No decided requests yet.' : 'No requests to show.')
      : `No ${bookingFilter === 'All' ? '' : bookingFilter.toLowerCase() + ' '}requests to show.`;
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  list.innerHTML = filtered.map(b => bookingCard(b, isAdmin)).join('');
}

// Approve / Reject: first click opens an inline confirm bar on the card, second click sends it.
document.getElementById('bk-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if(!btn) return;
  const card = btn.closest('.req');
  const act = btn.dataset.act;

  if(act === 'ask-approve' || act === 'ask-reject'){
    document.querySelectorAll('#bk-list .req.asking').forEach(c => c.classList.remove('asking', 'is-decline'));
    const decline = act === 'ask-reject';
    card.classList.add('asking');
    card.classList.toggle('is-decline', decline);
    card.dataset.decision = decline ? 'reject' : 'approve';
    card.querySelector('.req-confirm-text').textContent = decline
      ? `Reject the request for ${card.dataset.name}? The requester will see it as rejected.`
      : `Approve the request for ${card.dataset.name}? The requester will see it as approved.`;
    const go = card.querySelector('.req-btn.go');
    go.textContent = decline ? 'Yes, reject' : 'Yes, approve';
    const reasonBox = card.querySelector('.req-reason');
    if(reasonBox) reasonBox.value = '';
    (decline && reasonBox ? reasonBox : go).focus();
    return;
  }
  if(act === 'ask-cancel'){
    openCancelBookingModal(card.dataset.id, card.dataset.name, card.dataset.status);
    return;
  }
  if(act === 'cancel'){
    card.classList.remove('asking', 'is-decline');
    return;
  }
  if(act === 'confirm'){
    const decision = card.dataset.decision;
    btn.disabled = true;
    // Optional note, only sent when rejecting; the requester sees it on their request.
    const reason = decision === 'reject' ? (card.querySelector('.req-reason')?.value.trim() || '') : '';
    const {ok, data} = await apiAuthSend('POST', `/api/bookings/${card.dataset.id}/decide`, reason ? {decision, reason} : {decision});
    if(!ok){
      btn.disabled = false;
      toast(data.error || 'Could not update request');
      return;
    }
    toast(decision === 'approve' ? 'Request approved' : 'Request rejected');
    loadBookings();
  }
});

function openCancelBookingModal(id, name, status){
  document.getElementById('modal-box').innerHTML = `
    <h3>Cancel this ${status === 'Approved' ? 'booking' : 'request'}?</h3>
    <p class="note" style="margin:0 0 10px;">${escapeHtml(name)} — the time slot becomes free for others.</p>
    <div class="ci-foot"><button class="btn no" type="button" id="bk-cancel-back">Go back</button><button class="btn ok" type="button" id="bk-cancel-go">Yes, cancel it</button></div>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('bk-cancel-back').addEventListener('click', closeModal);
  document.getElementById('bk-cancel-go').addEventListener('click', async (e) => {
    e.target.disabled = true;
    const {ok, data} = await apiAuthSend('POST', `/api/bookings/${id}/cancel`);
    closeModal();
    toast(ok ? 'Cancelled' : (data.error || 'Could not cancel'));
    loadBookings();
  });
}

async function openBookingModal(preselectId){
  if(!resourceCache.length){
    const {ok, data} = await apiAuthGet('/api/resources');
    if(ok) resourceCache = data.resources;
  }
  // Offer every resource that can be booked: Available or In Use (an In Use
  // resource can still be reserved for a later time slot), but not
  // Maintenance or archived. Fetched fresh each time so a status change by an
  // admin is reflected; the backend re-checks this anyway.
  const isBookable = r => (r.status === 'Available' || r.status === 'In Use') && !r.is_archived;
  let bookable = resourceCache.filter(isBookable);
  const fresh = await apiAuthGet('/api/resources');
  if(fresh.ok) bookable = fresh.data.resources.filter(isBookable);
  const opts = bookable.length
    ? bookable.map(r => `<option value="${r.id}">${escapeHtml(r.name)}${r.status === 'In Use' ? ' (in use now)' : ''}</option>`).join('')
    : '<option value="" disabled selected>No resources available</option>';
  document.getElementById('modal-box').innerHTML = `
    <h3>New booking request</h3>
    <div id="booking-form-error" class="login-error"><span>⚠</span><span id="booking-form-error-text"></span></div>
    <form id="booking-form">
      <div class="field"><label>Resource</label><select id="bk-resource" required>${opts}</select></div>
      <div class="field"><label>Start</label><input id="bk-start" type="datetime-local" required></div>
      <div class="field"><label>End</label><input id="bk-end" type="datetime-local" required></div>
      <div class="field"><label>Purpose</label><input id="bk-purpose" required maxlength="255" placeholder="e.g. Sprint planning meeting"></div>
      <p class="note" style="margin:0 0 8px;">One booking can last up to 12 hours and be made up to 90 days ahead. You can have up to 5 requests waiting at a time.</p>
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:6px;">
        <button class="btn no" type="button" id="booking-form-cancel">Cancel</button>
        <button class="btn ok" type="submit">Submit</button>
      </div>
    </form>
  `;
  document.getElementById('modal-backdrop').classList.add('open');
  if(preselectId){
    const sel = document.getElementById('bk-resource');
    if(sel) sel.value = String(preselectId);
  }
  document.getElementById('booking-form-cancel').addEventListener('click', closeModal);
  document.getElementById('booking-form').addEventListener('submit', submitBookingForm);
}
document.getElementById('btn-new-booking').addEventListener('click', () => openBookingModal());

async function submitBookingForm(e){
  e.preventDefault();
  const errBox = document.getElementById('booking-form-error');
  const errText = document.getElementById('booking-form-error-text');
  errBox.classList.remove('show');

  const payload = {
    resource_id: Number(document.getElementById('bk-resource').value),
    start_time: toInstant(document.getElementById('bk-start').value),
    end_time: toInstant(document.getElementById('bk-end').value),
    purpose: document.getElementById('bk-purpose').value.trim()
  };

  const {ok, data} = await apiAuthSend('POST', '/api/bookings', payload);
  if(!ok){
    // SRS-3: missing/invalid info or an overlapping booking blocks submission with a message.
    errText.textContent = data.error || 'Could not submit request.';
    errBox.classList.add('show');
    return;
  }
  closeModal();
  toast('Request submitted');
  loadBookings();
}
