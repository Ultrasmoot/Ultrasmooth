/* ---------- Resource detail (click a card) ---------- */
async function openResourceDetail(id){
  const {ok, data} = await apiAuthGet(`/api/resources/${id}/detail`);
  if(!ok){ toast(data.error || 'Could not load the resource'); return; }
  const r = data.resource, staff = isStaffRole();
  const place = [r.building, r.floor, r.location].filter(Boolean).map(escapeHtml).join(' · ');
  const slots = data.schedule.length ? data.schedule.map(s => `
    <div class="rd-slot"><span>${s5When(s.start_time)} – ${s5Time(s.end_time)}</span>
      <span>${staff ? `${escapeHtml(s.requester_name)}${s.purpose ? ' · ' + escapeHtml(s.purpose) : ''}` : 'Booked'}</span></div>`).join('')
    : '<p class="note" style="margin:0;">No upcoming bookings — free to book.</p>';
  let staffHtml = '';
  if(staff){
    const using = data.in_use_by;
    staffHtml = `
      <h4 class="s5-sec">In use right now</h4>
      ${using ? `<div class="rd-slot"><span><b>${escapeHtml(using.name)}</b> since ${s5When(using.since)}</span>
          <span>until ${s5Time(using.booked_until)} ${using.overdue ? s5Badge('Overdue', 'b-rust') : ''}</span></div>`
        : '<p class="note" style="margin:0;">Nobody.</p>'}
      <h4 class="s5-sec">Repair history</h4>
      ${data.maintenance.length ? data.maintenance.map(m => `
        <div class="rd-slot"><span>${escapeHtml(m.description)}</span><span>${escapeHtml(m.status)} · ${escapeHtml(m.reporter_name)}</span></div>`).join('')
        : '<p class="note" style="margin:0;">No issues recorded.</p>'}
      <h4 class="s5-sec">Recent activity</h4>
      ${data.activity.length ? data.activity.map(a => `
        <div class="rd-slot"><span>${escapeHtml(a.action_label)} — ${escapeHtml(a.summary)}</span><span>${s5When(a.created_at)} · ${escapeHtml(a.actor_name)}</span></div>`).join('')
        : '<p class="note" style="margin:0;">Nothing yet.</p>'}`;
  }
  const canRequest = currentRole === 'user' && !r.is_archived && (r.status === 'Available' || r.status === 'In Use');
  document.getElementById('modal-box').innerHTML = `
    <div class="rcard-code">${escapeHtml(r.resource_code)}${r.is_archived ? ' · Archived' : ''}</div>
    <h3 style="margin:2px 0 8px;">${escapeHtml(r.name)}</h3>
    <div>${s5Badge(r.status, {Available:'b-green', 'In Use':'b-amber', Maintenance:'b-rust'}[r.status])}
      <span class="tag">#${escapeHtml(r.category)}</span><span class="tag plain">${escapeHtml(r.type)}</span></div>
    <div class="rd-line">
      ${place ? `<span>📍 ${place}</span>` : ''}
      ${r.capacity ? `<span>👥 Up to ${r.capacity} people</span>` : ''}
      <span>Owner: ${escapeHtml(r.owner)}</span>
    </div>
    ${r.features.length ? `<div style="margin:6px 0;">${r.features.map(f => `<span class="s5-pill">${escapeHtml(f)}</span>`).join(' ')}</div>` : ''}
    ${r.usage_notes ? `<p style="margin:10px 0; font-size:13.5px; color:var(--ink-soft); white-space:pre-line;">${escapeHtml(r.usage_notes)}</p>` : ''}
    <h4 class="s5-sec">Upcoming bookings</h4>${slots}
    ${staffHtml}
    <div class="ci-foot">
      <button class="btn no" type="button" id="rd-close">Close</button>
      <span><button class="btn" type="button" id="rd-calendar">Calendar</button>
      ${r.is_archived ? '' : '<button class="btn" type="button" id="rd-report">Report issue</button>'}
        ${canRequest ? ' <button class="btn ok" type="button" id="rd-book">Request</button>' : ''}</span>
    </div>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('rd-close').addEventListener('click', closeModal);
  /* Panisara */
  document.getElementById('rd-calendar').addEventListener('click', () => { closeModal(); showCalendarFor(id); });
  const rep = document.getElementById('rd-report');
  if(rep) rep.addEventListener('click', () => { closeModal(); openMaintenanceModal(id); });
  const book = document.getElementById('rd-book');
  if(book) book.addEventListener('click', () => { closeModal(); openBookingModal(id); });
}
const isStaffRole = () => currentRole === 'admin' || currentRole === 'professor';
