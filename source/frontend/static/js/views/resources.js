/* Resource Management */
let resourceCache = [];
let editingResourceId = null; // null = creating a new resource

function escapeHtml(s){
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function populateFilterOptions(resources){
  const catSel = document.getElementById('res-filter-category');
  const locSel = document.getElementById('res-filter-location');
  const prevCat = catSel.value, prevLoc = locSel.value;

  const categories = [...new Set(resources.map(r => r.category))].sort();
  const locations = [...new Set(resources.map(r => r.location))].sort();

  catSel.innerHTML = '<option value="">All categories</option>' +
    categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  locSel.innerHTML = '<option value="">All locations</option>' +
    locations.map(l => `<option value="${escapeHtml(l)}">${escapeHtml(l)}</option>`).join('');

  catSel.value = prevCat;
  locSel.value = prevLoc;
}

function renderResources(resources){
  const grid = document.getElementById('res-grid');
  const empty = document.getElementById('res-empty');
  document.getElementById('res-count').textContent = `${resources.length} resource${resources.length === 1 ? '' : 's'}`;

  if(resources.length === 0){
    grid.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  grid.innerHTML = resources.map(r => resourceCard(r, {manage: true})).join('');
}

async function loadResources(){
  const params = new URLSearchParams();
  const q = document.getElementById('res-search').value.trim();
  const category = document.getElementById('res-filter-category').value;
  const location = document.getElementById('res-filter-location').value;
  const statusEl = document.getElementById('res-filter-status');
  const availableOnly = document.getElementById('res-filter-availability').checked;
  // "Available now" is a separate filter dimension from the detailed
  // status dropdown (filter by category/location/availability
  // /status independently). When it's checked it takes priority so the
  // two controls never disagree silently.
  const status = availableOnly ? 'Available' : statusEl.value;
  statusEl.disabled = availableOnly;
  const sort = document.getElementById('res-sort').value;
  const showArchived = document.getElementById('res-show-archived').checked;
  if(q) params.set('q', q);
  if(category) params.set('category', category);
  if(location) params.set('location', location);
  if(status) params.set('status', status);
  if(sort) params.set('sort', sort);
  if(showArchived) params.set('include_archived', 'true');

  const {ok, data} = await apiAuthGet('/api/resources?' + params.toString());
  if(!ok){
    toast('Could not load resources');
    return;
  }
  resourceCache = data.resources;
  // Only rebuild the dropdown options from an unfiltered list, otherwise they shrink to the current result.
  if(!q && !category && !location && !status) populateFilterOptions(resourceCache);
  renderResources(resourceCache);
}

['res-search'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => loadResources());
});
['res-filter-category', 'res-filter-location', 'res-filter-status', 'res-sort', 'res-filter-availability', 'res-show-archived'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => loadResources());
});

// Edit / Archive / Request clicks on resource cards are handled by cardActionHandler() below.

function closeModal(){
  document.getElementById('modal-backdrop').classList.remove('open');
}

function openResourceModal(resourceId = null){
  editingResourceId = resourceId;
  const resource = resourceId ? resourceCache.find(r => r.id === resourceId) : null;
  // Maintenance is set/cleared only by maintenance records, so a
  // resource that is in Maintenance shows it locked, and nobody can pick it here.
  const statusLocked = resource?.status === 'Maintenance';

  document.getElementById('modal-box').innerHTML = `
    <div class="modal-wide">
    <h3>${resource ? 'Edit Resource' : 'Add Resource'}</h3>
    <div id="resource-form-error" class="login-error"><span>⚠</span><span id="resource-form-error-text"></span></div>
    <form id="resource-form" class="mgrid">
      <div class="field"><label>Name</label><input id="res-name" required value="${escapeHtml(resource?.name)}"></div>
      <div class="field"><label>Type</label><input id="res-type" required value="${escapeHtml(resource?.type)}"></div>
      <div class="field"><label>Category</label><input id="res-category" required value="${escapeHtml(resource?.category)}"></div>
      <div class="field"><label>Location</label><input id="res-location" required value="${escapeHtml(resource?.location)}"></div>
      <div class="field"><label>Building <small>(optional)</small></label><input id="res-building" maxlength="100" value="${escapeHtml(resource?.building)}"></div>
      <div class="field"><label>Floor <small>(optional)</small></label><input id="res-floor" maxlength="50" value="${escapeHtml(resource?.floor)}"></div>
      <div class="field"><label>Owner</label><input id="res-owner" required value="${escapeHtml(resource?.owner)}"></div>
      <div class="field"><label>Capacity — people <small>(optional, for rooms)</small></label><input id="res-capacity" type="number" min="1" max="100000" step="1" value="${escapeHtml(resource?.capacity ?? '')}"></div>
      <div class="field"><label>Facilities <small>(optional, separate with commas)</small></label><input id="res-features" maxlength="500" placeholder="Projector, Whiteboard, Wi-Fi" value="${escapeHtml((resource?.features || []).join(', '))}"></div>
      <div class="field">
        <label>Status</label>
        ${statusLocked ? `
        <select id="res-status" disabled><option selected>Maintenance</option></select>
        <p class="note" style="margin:6px 0 0;">Maintenance is set by reporting an issue. When the repair is done, return the resource to Available.</p>
        <button class="btn ok" type="button" id="res-restore" style="margin-top:8px;">Return to Available</button>` : `
        <select id="res-status">
          <option ${resource?.status === 'Available' || !resource ? 'selected' : ''}>Available</option>
          <option ${resource?.status === 'In Use' ? 'selected' : ''}>In Use</option>
        </select>`}
      </div>
      <div class="field span2"><label>What it can be used for <small>(optional)</small></label><textarea id="res-notes" rows="3" maxlength="1000" style="width:100%; font-family:inherit; font-size:13px; padding:8px; border:1px solid var(--line); border-radius:6px;">${escapeHtml(resource?.usage_notes)}</textarea></div>
      <div class="span2" style="display:flex; gap:8px; justify-content:flex-end; margin-top:2px;">
        <button class="btn no" type="button" id="resource-form-cancel">Cancel</button>
        <button class="btn ok" type="submit">Save</button>
      </div>
    </form>
    </div>
  `;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('resource-form-cancel').addEventListener('click', closeModal);
  document.getElementById('resource-form').addEventListener('submit', submitResourceForm);
  const restoreBtn = document.getElementById('res-restore');
  if(restoreBtn) restoreBtn.addEventListener('click', () => openRestoreConfirm(resourceId));
}
document.getElementById('btn-add-resource').addEventListener('click', () => openResourceModal(null));

async function submitResourceForm(e){
  e.preventDefault();
  const errBox = document.getElementById('resource-form-error');
  const errText = document.getElementById('resource-form-error-text');
  errBox.classList.remove('show');

  const payload = {
    name: document.getElementById('res-name').value.trim(),
    type: document.getElementById('res-type').value.trim(),
    category: document.getElementById('res-category').value.trim(),
    location: document.getElementById('res-location').value.trim(),
    owner: document.getElementById('res-owner').value.trim(),
    status: document.getElementById('res-status').value,
    // optional details (blank clears them)
    building: document.getElementById('res-building').value.trim() || null,
    floor: document.getElementById('res-floor').value.trim() || null,
    capacity: document.getElementById('res-capacity').value.trim() || null,
    features: document.getElementById('res-features').value,
    usage_notes: document.getElementById('res-notes').value.trim() || null
  };

  const method = editingResourceId ? 'PUT' : 'POST';
  const path = editingResourceId ? `/api/resources/${editingResourceId}` : '/api/resources';

  const {ok, data} = await apiAuthSend(method, path, payload);
  if(!ok){
    // missing/invalid data blocks saving with a validation message.
    errText.textContent = data.error || 'Could not save resource.';
    errBox.classList.add('show');
    return;
  }
  closeModal();
  loadResources();
}

async function archiveResource(id){
  // archiving hides the resource from the active list rather than deleting it.
  const {ok, data} = await apiAuthSend('POST', `/api/resources/${id}/archive`);
  if(!ok){
    toast(data.error || 'Could not archive resource');
    return;
  }
  toast('Resource archived');
  loadResources();
}

async function unarchiveResource(id){
  const {ok, data} = await apiAuthSend('POST', `/api/resources/${id}/unarchive`);
  if(!ok){
    toast(data.error || 'Could not unarchive resource');
    return;
  }
  toast('Resource unarchived');
  loadResources();
}

// Maintenance -> Available. Open issues of the resource are resolved together with it.
function openRestoreConfirm(id){
  const r = resourceCache.find(x => x.id === id);
  document.getElementById('modal-box').innerHTML = `
    <h3>Return to Available?</h3>
    <div id="restore-error" class="login-error"><span>⚠</span><span id="restore-error-text"></span></div>
    <p class="note" style="margin:0 0 14px;">${escapeHtml(r ? r.name : 'This resource')} will be set back to Available and can be booked again. Any open maintenance issues for it will be marked Resolved.</p>
    <div style="display:flex; gap:8px; justify-content:flex-end;">
      <button class="btn no" type="button" id="restore-cancel">Cancel</button>
      <button class="btn ok" type="button" id="restore-go">Yes, return to Available</button>
    </div>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('restore-cancel').addEventListener('click', closeModal);
  document.getElementById('restore-go').addEventListener('click', async (e) => {
    const go = e.currentTarget;
    go.disabled = true;
    document.getElementById('restore-error').classList.remove('show');
    const {ok, data} = await apiAuthSend('POST', `/api/resources/${id}/restore`);
    if(!ok){
      document.getElementById('restore-error-text').textContent = data.error || 'Could not update the resource.';
      document.getElementById('restore-error').classList.add('show');
      go.disabled = false;
      return;
    }
    closeModal();
    toast('Resource is Available again');
    loadResources();
  });
}
