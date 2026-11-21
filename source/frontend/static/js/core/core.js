/* ---------------- Roles ---------------- */
const ROLES = {
  user:      { label:'Lab User',      name:'Napakhet',    initials:'NP', canManage:false, canApprove:false },
  professor: { label:'Professor',     name:'Aj. Somchai',  initials:'AS', canManage:false, canApprove:false },
  admin:     { label:'Administrator', name:'System Admin', initials:'SA', canManage:true,  canApprove:true  }
};
let currentRole = 'admin';
let roleLocked = false; // true once a real backend login happens — no more "view as" switching

function applyRole(key){
  currentRole = key;
  document.body.dataset.role = key;
  const r = ROLES[key];
  const setText = (id, txt) => { const el = document.getElementById(id); if(el) el.textContent = txt; };
  setText('role-av', r.initials);
  setText('role-name', r.name);
  setText('role-label', r.label);
  setText('profile-name', r.name);     // side-menu account text (name is overridden by applyRealUser for real logins)
  setText('profile-status', r.label);
  document.querySelectorAll('#role-menu button').forEach(b=>b.classList.toggle('active', b.dataset.role===key));
  document.getElementById('role-menu').classList.remove('open');
}

function lockRoleSwitcher(){
  // Users can no longer switch roles as this was only for the demo.
  roleLocked = true;
  const menu = document.getElementById('role-menu');
  menu.innerHTML = `
    <div class="eyebrow">Signed in as</div>
    <div class="menu-user"><b id="role-name"></b><span id="role-email"></span><span id="role-label"></span></div>
    <button type="button" class="menu-logout" id="menu-logout"><b>Log out</b></button>
  `;
  document.getElementById('role-name').textContent = ROLES[currentRole].name;
  document.getElementById('role-email').textContent = currentUser ? currentUser.email : '';
  // detailed status (e.g. "Undergraduate Student Year 2") is shown here, in the dropdown
  document.getElementById('role-label').textContent = currentUser ? statusLabel(currentUser) : ROLES[currentRole].label;
  document.getElementById('menu-logout').addEventListener('click', signOut);
}

document.getElementById('role-chip').addEventListener('click', (e)=>{
  e.stopPropagation();
  document.getElementById('role-menu').classList.toggle('open');
});
document.getElementById('profile-info').addEventListener('click', (e)=>{
  e.stopPropagation();
  document.getElementById('role-menu').classList.toggle('open');
});
document.querySelectorAll('#role-menu button').forEach(b=>{
  b.addEventListener('click', ()=> applyRole(b.dataset.role));
});
document.addEventListener('click', ()=> document.getElementById('role-menu').classList.remove('open'));

/* ---------------- Nav (access-check tied to backend) ---------------- */
const titles = {
  home: ["Home", "You're signed in — more features arrive in later iterations"],
  resources: ["Resources", "Browse, search, and manage lab equipment and tools"],
  bookings: ["Requests", "Review and track lab resource bookings"],
  maintenance: ["Maintenance", "Report resource issues and track repairs"],
  checkin: ["Check in / Check out", "Check in to your approved bookings"],
  dashboard: ["Dashboard", "Lab status and resource utilization at a glance"],
  activity: ["Activity log", "Who did what, and when"],
  history: ["Check-in history", "Who used which resource, and when they checked in and out"],
  calendar: ["Resource Calendar", "See when a resource is already booked"],
  appointments: ["Appointments", "Ask a professor for advice, or answer students' requests"],
  access: ["User & Access", "Manage accounts, roles, and permissions"]
};
document.querySelectorAll('.nav-item').forEach(btn=>{
  btn.addEventListener('click', async ()=>{
    const key = btn.dataset.view;
    if(!key) return;  
    // verify access. Unlike the currentRole check above
    if(key === 'access'){
      const {ok} = await apiAuthGet('/api/admin/access-check');
      if(!ok){
        toast('Access denied — Administrator role required');
        return;
      }
    }

    document.querySelectorAll('.nav-item').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
    document.getElementById('view-'+key).classList.add('active');
    document.getElementById('page-title').textContent = titles[key][0];
    document.getElementById('page-desc').textContent = titles[key][1];
    document.body.dataset.view = key;
    window.scrollTo({top: 0});

    if(key === 'home'){ loadHome(); loadAnnouncements(); }
    if(key === 'resources') loadResources();
    if(key === 'bookings') loadBookings();
    if(key === 'maintenance') loadMaintenance();
    if(key === 'checkin') loadCheckin();
    if(key === 'dashboard') loadDashboard();
    if(key === 'activity') openActivity();
    if(key === 'history') openHistory();  
    if(key === 'calendar') openCalendar(); 
    if(key === 'appointments') loadAppointments();
    if(key === 'access') loadUsers();
  });
});

/* ---------------- Time zones ----------------
Convert local datetime to UTC with toInstant() so the server uses the same moment.*/
function toInstant(localValue){
  const d = new Date(localValue);
  return isNaN(d) ? localValue : d.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/* ---------------- Toast ---------------- */
function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=> t.classList.remove('show'), 2600);
}
// Show loading spinner, then update time; loader must return false on failure.
function setupRefreshButton(btnId, loader){
  const btn = document.getElementById(btnId);
  const stamp = document.createElement('span');
  stamp.className = 'refresh-stamp';
  stamp.setAttribute('role', 'status');
  stamp.setAttribute('aria-live', 'polite');
  btn.insertAdjacentElement('beforebegin', stamp);
  btn.addEventListener('click', async () => {
    if(btn.disabled) return;
    const label = btn.textContent;
    btn.disabled = true;
    btn.classList.add('is-loading');
    btn.textContent = 'Refreshing…';
    stamp.classList.remove('bad', 'flash');
    stamp.textContent = '';
    const started = Date.now();
    let ok = true;
    try{ ok = (await loader()) !== false; }catch(err){ ok = false; }
    // Loads are near-instant; keep the "Refreshing…" state visible long enough to notice.
    const wait = 600 - (Date.now() - started);
    if(wait > 0) await new Promise(r => setTimeout(r, wait));
    btn.disabled = false;
    btn.classList.remove('is-loading');
    btn.textContent = label;
    stamp.textContent = ok
      ? 'Updated ' + new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})
      : 'Refresh failed — try again';
    stamp.classList.toggle('bad', !ok);
    void stamp.offsetWidth;              
    stamp.classList.add('flash');
    if(ok) toast('Refreshed');
  });
}
