/* ---------------- User & Access (US-13): administrators manage accounts and roles ---------------- */
let usrList = [], usrTimer = null;
let usrView = 'cards';   // 'cards' or 'list' (not remembered: it starts as cards every time)
const USR_ROLE_OPTIONS = [['undergrad_student', 'Undergraduate Student'], ['phd_student', 'Ph.D. Student'],
                          ['professor', 'Professor'], ['admin', 'Lab Administrator']];

async function loadUsers(){
  const box = document.getElementById('usr-content');
  const qs = new URLSearchParams();
  const q = document.getElementById('usr-q').value.trim();
  if(q) qs.set('q', q);
  ['role', 'status'].forEach(k => { const v = document.getElementById('usr-' + k).value; if(v) qs.set(k, v); });
  const {ok, data} = await apiAuthGet('/api/admin/users' + (qs.toString() ? '?' + qs.toString() : ''));
  if(!ok){ box.innerHTML = `<p class="note">${escapeHtml(data.error || 'Could not load users')}</p>`; return; }
  usrList = data.users;
  renderUsers();
}

const UA_PERSON = '<svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="19" r="8" fill="#FBF8EF"/><path d="M8 48c2-11 10-15 16-15s14 4 16 15z" fill="#FBF8EF"/></svg>';
const ICON_MAIL = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3.5" width="12" height="9" rx="1.8" stroke="currentColor" stroke-width="1.3"/><path d="M2.6 4.6 8 8.6l5.4-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function userCard(u, myId){
  const mine = u.id === myId;
  const off = !u.is_active;
  const unverified = u.is_active && !u.email_verified;
  const statusText = off ? 'Deactivated' : (unverified ? 'Unverified' : 'Active');
  const statusCls = off ? 'st-off' : (unverified ? 'st-inuse' : 'st-available');
  // top line: student ID for students; the faculty name for everyone else (or whenever there is no ID)
  const code = u.student_id || u.faculty || (u.role === 'admin' ? 'Software Eng. Lab' : '—');
  const extra = (u.role === 'undergrad_student' && u.year) ? `Year ${u.year}` : (u.major || '');
  // professors: their expertise as #topics under the e-mail (students search by these)
  const topics = u.role === 'professor'
    ? (Array.isArray(u.expertise) ? u.expertise : String(u.expertise || '').split(',')).map(t => String(t).trim()).filter(Boolean)
    : [];
  const topicHtml = topics.length
    ? `<div class="tags">${topics.slice(0, 3).map(t => `<span class="tag exp">#${escapeHtml(t)}</span>`).join('')}${topics.length > 3 ? `<span class="tag exp" title="${escapeHtml(topics.slice(3).join(', '))}">+${topics.length - 3}</span>` : ''}</div>`
    : '';
  return `
    <article class="rcard ua-card ${off ? 'is-off' : ''}" data-role="${escapeHtml(u.role)}">
      <div class="rcard-art"><div class="ua-av">${UA_PERSON}</div><span class="rcard-status ${statusCls}">${statusText}</span></div>
      <div class="rcard-code">${escapeHtml(code)}</div>
      <h3 title="${escapeHtml(u.full_name || u.email)}">${escapeHtml(u.full_name || '(no name)')}${mine ? '<span class="ua-you">You</span>' : ''}</h3>
      <div class="pill" title="${escapeHtml(u.email)}">${ICON_MAIL}<span>${escapeHtml(u.email)}</span></div>
      ${topicHtml}<div class="tags"><span class="tag">${escapeHtml(u.role_label)}</span>${extra ? `<span class="tag plain">${escapeHtml(extra)}</span>` : ''}</div>
      <div class="rcard-actions">
        <button class="btn" type="button" data-usr-edit="${u.id}">Edit</button>
        ${u.is_active
          ? `<button class="btn no" type="button" data-usr-off="${u.id}" ${mine ? 'disabled title="You cannot deactivate your own account"' : ''}>Deactivate</button>`
          : `<button class="btn ok" type="button" data-usr-on="${u.id}">Reactivate</button>`}
      </div>
    </article>`;
}

// One account as a row of the list view (same buttons and data attributes as the card).
function userRow(u, myId){
  const mine = u.id === myId;
  const off = !u.is_active;
  const unverified = u.is_active && !u.email_verified;
  const statusText = off ? 'Deactivated' : (unverified ? 'Unverified' : 'Active');
  const statusCls = off ? 'st-off' : (unverified ? 'st-inuse' : 'st-available');
  const code = u.student_id || u.faculty || (u.role === 'admin' ? 'Software Eng. Lab' : '—');
  const extra = (u.role === 'undergrad_student' && u.year) ? ` · Year ${u.year}` : '';
  return `
    <div class="ua-row ${off ? 'is-off' : ''}" data-role="${escapeHtml(u.role)}" role="row">
      <div class="ua-c ua-name" role="cell"><span class="ua-dot">${UA_PERSON}</span><div class="ua-who"><div class="ua-nm"><b title="${escapeHtml(u.full_name || u.email)}">${escapeHtml(u.full_name || '(no name)')}</b>${mine ? '<span class="ua-you">You</span>' : ''}</div><div class="ua-mail" title="${escapeHtml(u.email)}">${escapeHtml(u.email)}</div></div></div>
      <div class="ua-c ua-role" role="cell"><span class="tag">${escapeHtml(u.role_label)}</span>${extra ? `<span class="ua-yr">${escapeHtml(extra.replace(' · ',''))}</span>` : ''}</div>
      <div class="ua-c ua-code" role="cell">${escapeHtml(code)}</div>
      <div class="ua-c" role="cell"><span class="ua-state ${statusCls}">${statusText}</span></div>
      <div class="ua-c ua-acts" role="cell">
        <button class="btn" type="button" data-usr-edit="${u.id}">Edit</button>
        ${u.is_active
          ? `<button class="btn no" type="button" data-usr-off="${u.id}" ${mine ? 'disabled title="You cannot deactivate your own account"' : ''}>Deactivate</button>`
          : `<button class="btn ok" type="button" data-usr-on="${u.id}">Reactivate</button>`}
      </div>
    </div>`;
}

function renderUsers(){
  const box = document.getElementById('usr-content');
  document.getElementById('usr-count').textContent = `${usrList.length} account${usrList.length === 1 ? '' : 's'}`;
  const asList = usrView === 'list';
  box.classList.toggle('grid', !asList);
  box.classList.toggle('ua-list', asList);
  document.querySelectorAll('#usr-view [data-usr-view]').forEach(b => {
    const on = b.dataset.usrView === usrView;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  if(!usrList.length){ box.innerHTML = '<p class="note" style="grid-column:1/-1;">No account matches.</p>'; return; }
  const myId = currentUser ? currentUser.id : null;
  box.innerHTML = asList
    ? `<div class="ua-row ua-headrow" role="row"><div class="ua-c">User</div><div class="ua-c">Role</div><div class="ua-c">ID / Faculty</div><div class="ua-c">Status</div><div class="ua-c"></div></div>`
      + usrList.map(u => userRow(u, myId)).join('')
    : usrList.map(u => userCard(u, myId)).join('');
}
document.getElementById('usr-view').addEventListener('click', (e) => {
  const b = e.target.closest('[data-usr-view]');
  if(!b || b.dataset.usrView === usrView) return;
  usrView = b.dataset.usrView;
  renderUsers();
});

function openUserModal(id){
  const u = id ? usrList.find(x => x.id === id) : null;
  if(id && !u) return;
  const self = !!(u && currentUser && u.id === currentUser.id);
  const v = (k) => escapeHtml(u && u[k] != null ? String(u[k]) : '');
  const role0 = u ? u.role : 'undergrad_student';
  const area = 'width:100%; font-family:inherit; font-size:13px; padding:8px; border:1px solid var(--line); border-radius:6px;';
  const created = u && u.created_at ? new Date(u.created_at).toLocaleString([], {dateStyle:'long', timeStyle:'short'}) : '';
  document.getElementById('modal-box').innerHTML = `
    <div class="modal-wide">
    <h3>${u ? 'Edit user' : 'Add user'}</h3>
    <div id="usr-form-error" class="login-error"><span>⚠</span><span id="usr-form-error-text"></span></div>
    <form id="usr-form" class="mgrid" autocomplete="off">
      <div class="field"><label>Full name</label><input id="usr-name" required maxlength="150" value="${v('full_name')}"></div>
      <div class="field"><label>Email</label><input id="usr-email" type="email" required maxlength="150" value="${v('email')}"></div>
      <div class="field"><label>Role</label>
        <select id="usr-role-sel" ${self ? 'disabled' : ''}>${USR_ROLE_OPTIONS.map(([val, label]) =>
          `<option value="${val}" ${val === role0 ? 'selected' : ''}>${label}</option>`).join('')}</select>
        ${self ? '<small>You cannot change your own role.</small>' : (u ? '<small>A role change takes effect immediately.</small>' : '')}</div>
      <div class="field" data-for="student"><label>Student ID <small>(10 digits, optional)</small></label>
        <input id="usr-sid" maxlength="10" inputmode="numeric" value="${v('student_id')}"></div>
      <div class="field" data-for="undergrad"><label>Class year</label>
        <select id="usr-year">${[1, 2, 3, 4, 5, 6].map(n => `<option value="${n}" ${(u && u.year === n) ? 'selected' : ''}>Year ${n}</option>`).join('')}</select></div>
      <div class="field"><label>Faculty <small>(optional)</small></label><input id="usr-faculty" maxlength="150" value="${v('faculty')}"></div>
      <div class="field"><label>Major <small>(optional)</small></label><input id="usr-major" maxlength="150" value="${v('major')}"></div>
      ${u ? `<div class="field"><label>Created at</label><input id="usr-created" value="${escapeHtml(created || '—')}" disabled></div>` : ''}
      <div class="field span2" data-for="professor"><label>Expertise <small>(topics separated by commas; students search by these)</small></label>
        <input id="usr-exp" maxlength="500" placeholder="e.g. Databases, Security" value="${v('expertise')}"></div>
      <div class="field span2" data-for="professor"><label>Short bio <small>(optional)</small></label>
        <textarea id="usr-bio" rows="3" maxlength="500" style="${area}">${v('bio')}</textarea></div>
      ${u ? '' : `<div class="field span2"><label>Temporary password <small>(at least 8 characters)</small></label>
        <input id="usr-pw" type="text" required minlength="8" maxlength="72" autocomplete="new-password">
        <small>Give it to the user; they can change it later with “Forgot password”.</small></div>`}
      <div class="ci-foot span2" style="margin-top:4px;"><button class="btn no" type="button" id="usr-cancel">Cancel</button>
        <button class="btn ok" type="submit" id="usr-save">${u ? 'Save changes' : 'Create account'}</button></div>
    </form>
    </div>`;
  const form = document.getElementById('usr-form');
  const roleSel = document.getElementById('usr-role-sel');
  const currentRoleValue = () => self ? u.role : roleSel.value;
  const sync = () => {
    const r = currentRoleValue();
    form.querySelector('[data-for="student"]').style.display = (r === 'undergrad_student' || r === 'phd_student') ? '' : 'none';
    form.querySelector('[data-for="undergrad"]').style.display = r === 'undergrad_student' ? '' : 'none';
    form.querySelectorAll('[data-for="professor"]').forEach(el => { el.style.display = r === 'professor' ? '' : 'none'; });
  };
  roleSel.addEventListener('change', sync);
  sync();
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('usr-cancel').addEventListener('click', closeModal);
  document.getElementById('usr-name').focus();
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errBox = document.getElementById('usr-form-error');
    errBox.classList.remove('show');
    const role = currentRoleValue();
    const val = (id) => document.getElementById(id).value.trim();
    const body = {full_name: val('usr-name'), email: val('usr-email'), role,
                  faculty: val('usr-faculty') || null, major: val('usr-major') || null};
    if(role === 'undergrad_student' || role === 'phd_student') body.student_id = val('usr-sid') || null;
    if(role === 'undergrad_student') body.year = Number(document.getElementById('usr-year').value);
    if(role === 'professor'){ body.expertise = val('usr-exp'); body.bio = val('usr-bio'); }
    if(!u) body.password = document.getElementById('usr-pw').value;
    const save = document.getElementById('usr-save');
    save.disabled = true;
    const {ok, data} = u ? await apiAuthSend('PUT', `/api/admin/users/${u.id}`, body)
                         : await apiAuthSend('POST', '/api/admin/users', body);
    save.disabled = false;
    if(!ok){
      document.getElementById('usr-form-error-text').textContent = data.error || 'Could not save the account.';
      errBox.classList.add('show');
      return;
    }
    closeModal();
    toast(u ? 'Changes saved' : 'Account created');
    loadUsers();
  });
}

function openUserToggleModal(id, activate){
  const u = usrList.find(x => x.id === id);
  if(!u) return;
  document.getElementById('modal-box').innerHTML = `
    <h3>${activate ? 'Reactivate this account?' : 'Deactivate this account?'}</h3>
    <p style="margin:0 0 6px;"><b>${escapeHtml(u.full_name || u.email)}</b> · ${escapeHtml(u.email)}</p>
    <p class="note" style="margin:0 0 12px;">${activate
      ? 'They will be able to log in again.'
      : 'They are signed out at once and cannot log in until you reactivate the account. Their bookings and history are kept.'}</p>
    <div id="usr-toggle-error" class="login-error"><span>⚠</span><span id="usr-toggle-error-text"></span></div>
    <div class="ci-foot"><button class="btn" type="button" id="usr-toggle-back">Go back</button>
      <button class="btn ${activate ? 'ok' : 'no'}" type="button" id="usr-toggle-go">${activate ? 'Yes, reactivate' : 'Yes, deactivate'}</button></div>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('usr-toggle-back').addEventListener('click', closeModal);
  document.getElementById('usr-toggle-go').addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    const {ok, data} = await apiAuthSend('POST', `/api/admin/users/${id}/${activate ? 'reactivate' : 'deactivate'}`);
    if(!ok){
      e.currentTarget.disabled = false;
      document.getElementById('usr-toggle-error-text').textContent = data.error || 'Could not change the account.';
      document.getElementById('usr-toggle-error').classList.add('show');
      return;
    }
    closeModal();
    toast(activate ? 'Account reactivated' : 'Account deactivated');
    loadUsers();
  });
}

document.getElementById('usr-add').addEventListener('click', () => openUserModal());
document.getElementById('usr-q').addEventListener('input', () => { clearTimeout(usrTimer); usrTimer = setTimeout(loadUsers, 250); });
['usr-role', 'usr-status'].forEach(id => document.getElementById(id).addEventListener('change', loadUsers));
document.getElementById('usr-content').addEventListener('click', (e) => {
  const t = e.target.closest('button');
  if(!t || t.disabled) return;
  if(t.dataset.usrEdit) openUserModal(Number(t.dataset.usrEdit));
  else if(t.dataset.usrOff) openUserToggleModal(Number(t.dataset.usrOff), false);
  else if(t.dataset.usrOn) openUserToggleModal(Number(t.dataset.usrOn), true);
});
