/* wired to real backend */
const API_BASE = '/api/auth';
// Backend roles (phd_student/undergrad_student/professor/admin) map
// onto the frontend's display roles (user/professor/admin).
const BACKEND_TO_UI_ROLE = {
  phd_student: 'user', undergrad_student: 'user',
  professor: 'professor', admin: 'admin'
};

const loginError = document.getElementById('login-error');
const loginErrorText = document.getElementById('login-error-text');
const createError = document.getElementById('create-error');
const createErrorText = document.getElementById('create-error-text');

function showLoginError(msg){
  loginErrorText.textContent = msg;
  loginError.classList.add('show');
}
// e-mail verification
const loginNotice = document.getElementById('login-notice');
const loginNoticeText = document.getElementById('login-notice-text');
const loginResendRow = document.getElementById('login-resend-row');
let verifyEmailAddress = '';   // address a verification link was (or should be) sent to

function showLoginNotice(msg){
  loginNoticeText.textContent = msg;
  loginNotice.classList.add('show');
}
function showResendLink(email){
  verifyEmailAddress = email || verifyEmailAddress;
  loginResendRow.style.display = '';
}
async function resendVerification(){
  const email = verifyEmailAddress || document.getElementById('login-email').value.trim();
  if(!email){ showLoginError('Enter your email above first.'); return; }
  loginError.classList.remove('show');
  try{
    const {ok, data} = await apiPost('/resend-verification', {email});
    if(ok) showLoginNotice(data.message || 'A new verification link has been sent.');
    else showLoginError(data.error || 'Could not send the email. Please try again.');
  } catch(err){
    showLoginError('Could not reach the server. Is the backend running?');
  }
}
document.getElementById('login-resend').addEventListener('click', resendVerification);
document.getElementById('login-resend').addEventListener('keydown', (e) => {
  if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); resendVerification(); }
});

function showCreateError(msg){
  createErrorText.textContent = msg;
  createError.classList.add('show');
}

let currentUser = null;

// Detailed status shown in the account dropdown (the side menu itself only shows the short role label).
const BACKEND_ROLE_LABEL = {
  phd_student: 'Ph.D. Student',
  undergrad_student: 'Undergraduate Student',
  professor: 'Professor',
  admin: 'Lab Administrator'
};
function statusLabel(user){
  const base = BACKEND_ROLE_LABEL[user.role] || user.role;
  // class year only exists for undergraduate students
  return (user.role === 'undergrad_student' && user.year) ? `${base} Year ${user.year}` : base;
}

function applyRealUser(user){
  currentUser = user;
  const uiRole = BACKEND_TO_UI_ROLE[user.role] || 'user';
  ROLES[uiRole] = {
    ...ROLES[uiRole],
    label: ROLES[uiRole].label,
    name: user.full_name || user.email,
    initials: (user.full_name || user.email).split(' ').map(w=>w[0]).slice(0,2).join('').toUpperCase()
  };
  applyRole(uiRole);
  lockRoleSwitcher();
  const displayName = user.full_name || user.email;
  const pn = document.getElementById('profile-name');
  pn.textContent = displayName;
  pn.title = displayName;
  // side-menu status: the user's actual role (no class year); admin/professor keep their existing label
  const SIDEBAR_STATUS = {undergrad_student:'Undergraduate Student', phd_student:'Ph.D. Student'};
  document.getElementById('profile-status').textContent = SIDEBAR_STATUS[user.role] || ROLES[uiRole].label;
}

function signIn(token, user){
  localStorage.setItem('vase_token', token);
  localStorage.setItem('vase_user', JSON.stringify(user));
  loginError.classList.remove('show');
  createError.classList.remove('show');
  document.body.classList.add('authed');
  applyRealUser(user);
  loadAnnouncements();
  loadHome();
  startNotifications();   // the bell
}

function signOut(){
  // JWTs are stateless, so logging out is just discarding the token
  // client-side; reloading resets all in-memory app state cleanly.
  localStorage.removeItem('vase_token');
  localStorage.removeItem('vase_user');
  window.location.reload();
}

// An expired/invalid token on an authenticated call: drop the session and
// reload, which lands on the login page instead of leaving a dead screen.
function handleExpiredSession(){
  if(!localStorage.getItem('vase_token')) return;
  localStorage.removeItem('vase_token');
  localStorage.removeItem('vase_user');
  window.location.reload();
}

async function apiPost(path, body){
  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json().catch(()=>({}));
  return {ok: res.ok, status: res.status, data};
}

// Generic authenticated GET, used for the /me restore check and for
// server-side-enforced role gates like /api/admin/access-check.
async function apiAuthGet(path){
  const token = localStorage.getItem('vase_token');
  try{
    const res = await fetch(path, {
      headers: token ? {'Authorization': 'Bearer ' + token} : {}
    });
    const data = await res.json().catch(()=>({}));
    if(res.status === 401) handleExpiredSession();
    if(!res.ok && !data.error) data.error = `Server error (${res.status}). Please try again.`;
    return {ok: res.ok, status: res.status, data};
  }catch(err){
    return {ok: false, status: 0, data: {error: 'Cannot reach the server. Check your connection and try again.'}};
  }
}

// Generic authenticated write (POST/PUT), used by Resource Management
// same Bearer-token pattern as apiAuthGet, with a JSON body.
async function apiAuthSend(method, path, body){
  const token = localStorage.getItem('vase_token');
  try{
    const res = await fetch(path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? {'Authorization': 'Bearer ' + token} : {})
      },
      body: body !== undefined ? JSON.stringify(body) : undefined
    });
    const data = await res.json().catch(()=>({}));
    if(res.status === 401) handleExpiredSession();
    if(!res.ok && !data.error) data.error = `Server error (${res.status}). Please try again.`;
    return {ok: res.ok, status: res.status, data};
  }catch(err){
    return {ok: false, status: 0, data: {error: 'Cannot reach the server. Check your connection and try again.'}};
  }
}

// Restores the session on page load/refresh
async function restoreSession(){
  const token = localStorage.getItem('vase_token');
  if(!token) return;
  const {ok, data} = await apiAuthGet(API_BASE + '/me');
  if(!ok || !data.user){
    localStorage.removeItem('vase_token');
    localStorage.removeItem('vase_user');
    return;
  }
  signIn(token, data.user);
}
