/* ---------- Appointments ---------- */
let apptProfessors = [], apptMine = [], apptQuery = '', apptTag = 'All';

const APPT_BADGE = {Pending:'b-amber', Accepted:'b-green', Declined:'b-rust', Cancelled:'b-faint', Expired:'b-faint'};
const apptStatus = (a) => a.expired ? 'Expired' : a.status;
setupRefreshButton('btn-refresh-appointments', () => loadAppointments());

async function loadAppointments(){
  const box = document.getElementById('appt-content');
  renderApptTabs();  /* Panisara */
  if(currentRole === 'professor'){
    if(apptView === 'calendar') return loadProfessorCalendar();  /* Panisara */
    const {ok, data} = await apiAuthGet('/api/appointments/inbox');
    if(!ok){ box.innerHTML = `<p class="note">${escapeHtml(data.error || 'Could not load requests')}</p>`; return false; }
    renderProfessorInbox(data.appointments);
    return true;
  }
  const [p, m] = await Promise.all([apiAuthGet('/api/appointments/professors'), apiAuthGet('/api/appointments/mine')]);
  if(!p.ok || !m.ok){ box.innerHTML = `<p class="note">${escapeHtml((p.data && p.data.error) || (m.data && m.data.error) || 'Could not load appointments')}</p>`; return false; }
  apptProfessors = p.data.professors;
  apptMine = m.data.appointments;
  renderStudentAppointments();
  return true;
}

function renderStudentAppointments(){
  const box = document.getElementById('appt-content');
  const tags = ['All'];
  apptProfessors.forEach(pr => pr.expertise.forEach(t => { if(!tags.includes(t)) tags.push(t); }));
  const q = apptQuery.trim().toLowerCase();
  const list = apptProfessors.filter(pr =>
    (apptTag === 'All' || pr.expertise.includes(apptTag)) &&
    (!q || `${pr.name} ${pr.expertise.join(' ')} ${pr.bio}`.toLowerCase().includes(q)));
  const mineHtml = apptMine.length ? apptMine.map(a => {
    const st = apptStatus(a);
    return `
    <div class="appt-item" data-st="${st}">
      <div class="appt-row"><b>${escapeHtml(a.topic)}</b>${s5Badge(st, APPT_BADGE[st])}</div>
      <p>with <b>${escapeHtml(a.professor_name)}</b> · ${s5When(a.start_time)} – ${s5Time(a.end_time)}</p>
      ${a.details ? `<p>${escapeHtml(a.details)}</p>` : ''}
      ${a.decision_reason ? `<p><b>Reason:</b> ${escapeHtml(a.decision_reason)}</p>` : ''}
      ${(a.status === 'Pending' && !a.expired) || (a.status === 'Accepted' && new Date(a.start_time) > new Date()) ? `<div class="appt-acts"><button class="btn" type="button" data-appt-cancel="${a.id}">${a.status === 'Accepted' ? 'Cancel appointment' : 'Cancel request'}</button></div>` : ''}
    </div>`;
  }).join('') : '<p class="note">You have not asked anyone yet.</p>';
  // keep the Refresh button alive across re-renders: park it back in the top bar before replacing the markup
  const refreshWrap = document.querySelector('#view-appointments .appt-refresh');
  const topBar = document.querySelector('#view-appointments .appt-top');
  if(refreshWrap && topBar) topBar.appendChild(refreshWrap);
  box.innerHTML = `
    <p class="note" style="margin:0 0 12px;">Not sure who to ask? Search by the topic you need help with — each professor lists what they are good at.</p>
    <div class="s5-filters appt-search-row"><div class="appt-search-box"><label for="appt-search">Search</label>
      <input id="appt-search" style="width:100%;" placeholder="A name or a topic, e.g. testing, database, security" value="${escapeHtml(apptQuery)}"></div><div id="appt-refresh-slot"></div></div>
    <div class="seg" style="margin-bottom:14px; flex-wrap:wrap;">${tags.map(t => `<button class="filter-chip ${t === apptTag ? 'active' : ''}" type="button" data-appt-tag="${escapeHtml(t)}">${escapeHtml(t)}</button>`).join('')}</div>
    <div class="prof-grid">${list.length ? list.map(pr => `
      <div class="prof-card">
        <div class="prof-head">${profAvatar(pr.id)}<div><h3>${escapeHtml(pr.name)}</h3>
          <div>${pr.expertise.map(t => `<span class="s5-pill">${escapeHtml(t)}</span>`).join(' ')}</div></div></div>
        <p class="prof-bio">${escapeHtml(pr.bio)}</p>
        <button class="btn ok" type="button" data-appt-ask="${pr.id}">Request appointment</button>
      </div>`).join('') : '<p class="note">No professor matches — try another topic.</p>'}</div>
    <h3 class="s5-sec">My appointments</h3>${mineHtml}`;
  const slot = document.getElementById('appt-refresh-slot');
  if(slot && refreshWrap) slot.appendChild(refreshWrap);
  const search = document.getElementById('appt-search');
  search.addEventListener('input', () => {
    apptQuery = search.value;
    const pos = search.selectionStart;
    renderStudentAppointments();
    const again = document.getElementById('appt-search');
    again.focus(); again.setSelectionRange(pos, pos);
  });
}

function renderProfessorInbox(items){
  const box = document.getElementById('appt-content');
  const waiting = items.filter(a => a.status === 'Pending' && !a.expired);
  const rest = items.filter(a => !(a.status === 'Pending' && !a.expired)).reverse();
  const card = (a, actions) => {
    const st = apptStatus(a);
    return `
    <div class="appt-item" data-st="${st}">
      <div class="appt-row"><b>${escapeHtml(a.topic)}</b>${s5Badge(st, APPT_BADGE[st])}</div>
      <p><b>${escapeHtml(a.student_name)}</b> · ${s5When(a.start_time)} – ${s5Time(a.end_time)}</p>
      ${a.details ? `<p>${escapeHtml(a.details)}</p>` : ''}
      ${a.decision_reason ? `<p><b>Reason:</b> ${escapeHtml(a.decision_reason)}</p>` : ''}
      ${actions ? `<div class="appt-acts"><button class="btn no" type="button" data-appt-decline="${a.id}">Decline</button>
        <button class="btn ok" type="button" data-appt-accept="${a.id}">Accept</button></div>` : ''}
    </div>`;
  };
  box.innerHTML = `
    <h3 class="s5-sec">Waiting for your answer (${waiting.length})</h3>
    ${waiting.map(a => card(a, true)).join('') || '<p class="note">All caught up.</p>'}
    <h3 class="s5-sec">Answered and closed</h3>
    ${rest.map(a => card(a, false)).join('') || '<p class="note">Nothing yet.</p>'}`;
}

function defaultAppointmentTime(){
  const d = new Date(Date.now() + 24 * 3600 * 1000);
  d.setHours(10, 0, 0, 0);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function openAppointmentModal(professorId){
  const pr = apptProfessors.find(x => x.id === professorId);
  if(!pr) return;
  document.getElementById('modal-box').innerHTML = `
    <h3>Request an appointment</h3>
    <div class="prof-head" style="margin-bottom:10px;">${profAvatar(pr.id)}<div><b>${escapeHtml(pr.name)}</b>
      <div>${pr.expertise.map(t => `<span class="s5-pill">${escapeHtml(t)}</span>`).join(' ')}</div></div></div>
    <div id="appt-form-error" class="login-error"><span>⚠</span><span id="appt-form-error-text"></span></div>
    <form id="appt-form">
      <div class="field"><label>Topic</label><input id="appt-topic" required minlength="3" maxlength="100" placeholder="What do you want to talk about?"></div>
      <div class="field"><label>More details <small>(optional)</small></label><textarea id="appt-details" rows="3" maxlength="500" placeholder="Describe the problem so the professor can decide" style="width:100%; font-family:inherit; font-size:13px; padding:8px; border:1px solid var(--line); border-radius:6px;"></textarea></div>
      <div class="field"><label>Preferred date and time <small>(30 minutes)</small></label><input id="appt-when" type="datetime-local" required value="${defaultAppointmentTime()}"></div>
      <div class="ci-foot"><button class="btn no" type="button" id="appt-cancel">Cancel</button><button class="btn ok" type="submit">Send request</button></div>
    </form>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('appt-cancel').addEventListener('click', closeModal);
  document.getElementById('appt-topic').focus();
  document.getElementById('appt-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('appt-form-error').classList.remove('show');
    const {ok, data} = await apiAuthSend('POST', '/api/appointments', {
      professor_id: professorId,
      topic: document.getElementById('appt-topic').value.trim(),
      details: document.getElementById('appt-details').value.trim() || null,
      start_time: toInstant(document.getElementById('appt-when').value)
    });
    if(!ok){
      document.getElementById('appt-form-error-text').textContent = data.error || 'Could not send the request.';
      document.getElementById('appt-form-error').classList.add('show');
      return;
    }
    closeModal();
    toast(`Request sent to ${pr.name}`);
    loadAppointments();
  });
}

function openDeclineModal(id){
  document.getElementById('modal-box').innerHTML = `
    <h3>Decline this request?</h3>
    <div class="field"><label>Reason <small>(optional — the student will see it)</small></label><input id="appt-reason" maxlength="255" placeholder="e.g. I am travelling that week"></div>
    <div class="ci-foot"><button class="btn no" type="button" id="appt-back">Go back</button><button class="btn ok" type="button" id="appt-go">Yes, decline</button></div>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('appt-reason').focus();
  document.getElementById('appt-back').addEventListener('click', closeModal);
  document.getElementById('appt-go').addEventListener('click', async () => {
    const reason = document.getElementById('appt-reason').value.trim();
    const {ok, data} = await apiAuthSend('POST', `/api/appointments/${id}/decide`, reason ? {decision: 'decline', reason} : {decision: 'decline'});
    closeModal();
    toast(ok ? 'Request declined' : (data.error || 'Could not decline'));
    loadAppointments();
  });
}

document.getElementById('appt-content').addEventListener('click', async (e) => {
  const t = e.target.closest('button');
  if(!t) return;
  if(t.dataset.apptTag !== undefined){ apptTag = t.dataset.apptTag; renderStudentAppointments(); }
  else if(t.dataset.apptAsk) openAppointmentModal(Number(t.dataset.apptAsk));
  else if(t.dataset.apptAccept){
    t.disabled = true;
    const {ok, data} = await apiAuthSend('POST', `/api/appointments/${t.dataset.apptAccept}/decide`, {decision: 'accept'});
    toast(ok ? 'Appointment accepted' : (data.error || 'Could not accept'));
    loadAppointments();
  }
  else if(t.dataset.apptDecline) openDeclineModal(Number(t.dataset.apptDecline));
  else if(t.dataset.apptCancel){
    t.disabled = true;
    const {ok, data} = await apiAuthSend('POST', `/api/appointments/${t.dataset.apptCancel}/cancel`);
    toast(ok ? 'Cancelled' : (data.error || 'Could not cancel'));
    loadAppointments();
  }
});
