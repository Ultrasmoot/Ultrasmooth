/* Google Sign-In (real, via Google Identity Services) */
let pendingGoogleProfile = null; // holds {email, full_name} for display while a first-time Google user picks a role
let pendingGoogleCredential = null; // Google ID token, re-sent so the backend can verify it again

async function handleGoogleCredential(response){
  loginError.classList.remove('show');
  const {ok, data} = await apiPost('/google', {credential: response.credential});
  if(!ok){
    showLoginError(data.error || 'Google sign-in failed.');
    return;
  }
  if(data.needs_role){
    // First-time Google sign-in: no role on file yet — ask before creating the account.
    pendingGoogleProfile = data;
    pendingGoogleCredential = response.credential;
    document.getElementById('g-profile-name').textContent = data.full_name || data.email;
    document.getElementById('g-profile-email').textContent = data.email;
    showAuthView('complete-profile');
    return;
  }
  signIn(data.token, data.user);
}

window.addEventListener('load', () => {
  if(!window.google || !google.accounts){
    // GSI script failed to load leave the button inert rather than crash.
    return;
  }
  google.accounts.id.initialize({
    client_id: window.GOOGLE_CLIENT_ID,
    callback: handleGoogleCredential
  });
});

document.getElementById('btn-google-login').addEventListener('click', () => {
  if(!window.google || !google.accounts){
    showLoginError('Google Sign-In script did not load. Check your connection and try again.');
    return;
  }
  google.accounts.id.prompt();
});

document.getElementById('complete-profile-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  if(!pendingGoogleProfile) return;
  const errBox = document.getElementById('complete-profile-error');
  const showErr = (msg) => {
    document.getElementById('complete-profile-error-text').textContent = msg;
    errBox.classList.add('show');
  };
  errBox.classList.remove('show');

  const role = document.getElementById('complete-profile-role').value;
  const payload = {credential: pendingGoogleCredential, role};
  // Undergraduate students must also pick their class year.
  if(role === 'undergrad_student'){
    const year = document.getElementById('complete-profile-year').value;
    if(!year){
      showErr('Please select your year.');
      return;
    }
    payload.year = Number(year);
  }

  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try{
    const {ok, data} = await apiPost('/google/complete-profile', payload);
    if(!ok){
      showErr(data.error || 'Could not complete sign-up.');
      return;
    }
    pendingGoogleProfile = null;
    pendingGoogleCredential = null;
    signIn(data.token, data.user);
  }catch(err){
    showErr('Could not reach the server. Please try again.');
  }finally{
    submitBtn.disabled = false;
  }
});

// Show the Year field only for undergraduate students; clear it otherwise.
document.getElementById('complete-profile-role').addEventListener('change', (e) => {
  const isUndergrad = e.target.value === 'undergrad_student';
  document.getElementById('complete-profile-year-field').style.display = isUndergrad ? 'block' : 'none';
  if(!isUndergrad) document.getElementById('complete-profile-year').value = '';
});

// Leave the first-time Google sign-up without finishing it (nothing was created yet).
document.getElementById('complete-profile-cancel').addEventListener('click', () => {
  pendingGoogleProfile = null;
  pendingGoogleCredential = null;
  document.getElementById('complete-profile-form').reset();
  document.getElementById('complete-profile-year-field').style.display = 'none';
  document.getElementById('complete-profile-error').classList.remove('show');
  showAuthView('login');
});

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  loginError.classList.remove('show');
  loginNotice.classList.remove('show');
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  if(!email || !password){
    showLoginError('Email and password are required.');
    return;
  }

  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try{
    const {ok, data} = await apiPost('/login', {email, password});
    if(!ok){
      showLoginError(data.error || 'Invalid email or password.');
      if(data.needs_verification) showResendLink(data.email || email);
      return;
    }
    signIn(data.token, data.user);
  } catch(err){
    showLoginError('Could not reach the server. Is the backend running?');
  } finally {
    submitBtn.disabled = false;
  }
});

function showAuthView(view){
  document.getElementById('login-view').classList.toggle('active', view === 'login');
  document.getElementById('create-view').classList.toggle('active', view === 'create');
  document.getElementById('complete-profile-view').classList.toggle('active', view === 'complete-profile');
  document.getElementById('forgot-password-view').classList.toggle('active', view === 'forgot-password');
  document.getElementById('reset-password-view').classList.toggle('active', view === 'reset-password');
}

function togglePw(id){
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}


document.addEventListener('click', (e) => {
  const pw = e.target.closest('[data-toggle-pw]');
  if(pw){ togglePw(pw.dataset.togglePw); return; }
  const view = e.target.closest('[data-auth-view]');
  if(view) showAuthView(view.dataset.authView);
});

// Year only applies to undergraduate students — Ph.D. students don't
// have a class year in this system. Student ID applies to everyone.
const STUDENT_ROLES = ['undergrad_student'];
document.getElementById('create-role').addEventListener('change', (e) => {
  const isStudent = STUDENT_ROLES.includes(e.target.value);
  document.getElementById('student-fields').style.display = isStudent ? 'block' : 'none';
});

const studentIdInput = document.getElementById('create-student-id');
studentIdInput.addEventListener('input', () => {
  // Digits only, 10 characters max.
  studentIdInput.value = studentIdInput.value.replace(/\D/g, '').slice(0, 10);
});

document.getElementById('create-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  createError.classList.remove('show');

  const sid = studentIdInput.value;
  if(sid.length !== 10){
    showCreateError('Student ID must be exactly 10 digits.');
    return;
  }

  const email = document.getElementById('create-email').value.trim();
  if(!email.includes('@')){
    showCreateError('Please enter a valid email address (must contain @).');
    return;
  }

  const password = document.getElementById('create-password').value;
  const confirmPassword = document.getElementById('create-confirm-password').value;
  if(password !== confirmPassword){
    showCreateError('Passwords do not match.');
    return;
  }

  const firstName = document.getElementById('create-first-name').value.trim();
  const lastName = document.getElementById('create-last-name').value.trim();
  const role = document.getElementById('create-role').value;
  const year = document.getElementById('create-year').value;
  if(role === 'undergrad_student' && !year){
    showCreateError('Please select your year.');
    return;
  }

  const payload = {
    student_id: sid,
    full_name: `${firstName} ${lastName}`.trim(),
    faculty: document.getElementById('create-faculty').value.trim(),
    major: document.getElementById('create-major').value.trim(),
    email, role, password
  };
  if(role === 'undergrad_student') payload.year = Number(year);

  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try{
    const {ok, data} = await apiPost('/signup', payload);
    if(!ok){
      showCreateError(data.error || 'Could not create account.');
      return;
    }
    // Sign-up is limited to Ph.D./Undergraduate Student (see dropdown options).
    // Lab Admin / Professor accounts are assigned later by an Administrator
    // the account is usable only after the emailed link is opened.
    createError.classList.remove('show');
    loginError.classList.remove('show');
    document.getElementById('login-email').value = data.email || payload.email || '';
    showLoginNotice(data.message || 'Account created. Check your email for a verification link, then log in.');
    showResendLink(data.email || payload.email);
    showAuthView('login');
  } catch(err){
    showCreateError('Could not reach the server. Is the backend running?');
  } finally {
    submitBtn.disabled = false;
  }
});

// Shared page-number bar used by Activity log and Check-in history (needs actPageList from insights.js).
// Buttons carry data-page; each page wires its own click handler on the container.
function renderPager(containerId, label, page, pages){
  const end = document.getElementById(containerId);
  if(pages <= 1){ end.innerHTML = ''; return; }
  const btn = (text, target, extra = '', aria = '') =>
    `<button type="button" class="act-pg ${extra}" data-page="${target}" ${aria}>${text}</button>`;
  end.innerHTML = `<nav class="act-pager" aria-label="${label}">`
    + btn('‹ Prev', page - 1, '', `aria-label="Previous page"${page <= 1 ? ' disabled' : ''}`)
    + actPageList(page, pages).map(p => p === '…'
        ? '<span class="act-gap">…</span>'
        : btn(p, p, p === page ? 'on' : '', `aria-label="Page ${p}"${p === page ? ' aria-current="page"' : ''}`)).join('')
    + btn('Next ›', page + 1, '', `aria-label="Next page"${page >= pages ? ' disabled' : ''}`)
    + '</nav>';
}
