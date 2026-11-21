/*  Announcements  */
async function loadAnnouncements(){
  const {ok, data} = await apiAuthGet('/api/announcements');
  if(!ok){
    toast(data.error || 'Could not load announcements');
    return;
  }
  renderAnnouncements(data.announcements);
}

function renderAnnouncements(items){
  const list = document.getElementById('announcements-list');
  const empty = document.getElementById('announcements-empty');
  if(!items.length){
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  const me = currentUser; // set in applyRealUser(); null if not yet restored
  // The author or an administrator may pin / delete (the server enforces the same rule).
  const mine = a => !!me && (me.id === a.author_id || me.role === 'admin');
  list.innerHTML = items.map(a => `
    <article class="ann ${a.is_pinned ? 'pinned' : ''}">
      <div class="ann-top">
        <div class="ann-title">
          ${a.is_pinned ? '<span class="badge b-amber">Pinned</span>' : ''}
          <b>${escapeHtml(a.title)}</b>
        </div>
        <div class="ann-actions">
          ${mine(a) ? `<button class="btn req-announcer" type="button" data-act="pin" data-id="${a.id}">${a.is_pinned ? 'Unpin' : 'Pin'}</button>` : ''}
          ${mine(a) ? `<button class="btn no" type="button" data-act="delete" data-id="${a.id}">Delete</button>` : ''}
        </div>
      </div>
      <p class="ann-body">${escapeHtml(a.body)}</p>
      <p class="ann-meta">Posted ${new Date(a.created_at).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})}</p>
    </article>
  `).join('');
}

document.getElementById('announcements-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-act]');
  if(!btn) return;
  if(btn.dataset.act === 'pin'){
    const {ok, data} = await apiAuthSend('POST', `/api/announcements/${btn.dataset.id}/pin`);
    if(!ok){ toast(data.error || 'Could not update'); return; }
    loadAnnouncements();
  } else if(btn.dataset.act === 'delete'){
    const {ok, data} = await apiAuthSend('DELETE', `/api/announcements/${btn.dataset.id}`);
    if(!ok){ toast(data.error || 'Could not delete'); return; }
    toast('Announcement deleted');
    loadAnnouncements();
  }
});

document.getElementById('btn-new-announcement').addEventListener('click', () => {
  document.getElementById('modal-box').innerHTML = `
    <h3>New announcement</h3>
    <div id="announcement-form-error" class="login-error"><span>⚠</span><span id="announcement-form-error-text"></span></div>
    <form id="announcement-form">
      <div class="field"><label>Title</label><input id="an-title" required maxlength="150" placeholder="e.g. Fume hood maintenance this Friday"></div>
      <div class="field"><label>Body</label><textarea id="an-body" required rows="4" style="width:100%; font-family:inherit; font-size:13px; padding:8px; border:1px solid var(--line); border-radius:6px;"></textarea></div>
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:6px;">
        <button class="btn no" type="button" id="announcement-form-cancel">Cancel</button>
        <button class="btn ok" type="submit">Post</button>
      </div>
    </form>
  `;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('announcement-form-cancel').addEventListener('click', closeModal);
  document.getElementById('announcement-form').addEventListener('submit', submitAnnouncementForm);
});

async function submitAnnouncementForm(e){
  e.preventDefault();
  const errBox = document.getElementById('announcement-form-error');
  const errText = document.getElementById('announcement-form-error-text');
  errBox.classList.remove('show');

  const payload = {
    title: document.getElementById('an-title').value.trim(),
    body: document.getElementById('an-body').value.trim()
  };
  const {ok, data} = await apiAuthSend('POST', '/api/announcements', payload);
  if(!ok){
    errText.textContent = data.error || 'Could not post announcement.';
    errBox.classList.add('show');
    return;
  }
  closeModal();
  toast('Announcement posted');
  loadAnnouncements();
}

document.getElementById('modal-backdrop').addEventListener('click', (e) => {
  if(e.target.id === 'modal-backdrop') closeModal();
});
