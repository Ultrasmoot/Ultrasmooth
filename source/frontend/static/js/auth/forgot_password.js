/* Napakhet */
/* ---------------- Forgot Password ---------------- */
document.getElementById('forgot-password-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('forgot-email').value.trim();
  const msgBox = document.getElementById('forgot-password-message');
  const submitBtn = e.target.querySelector('button[type="submit"]');

  submitBtn.disabled = true;
  try{
    const {data} = await apiPost('/forgot-password', {email});
    // Same message whether or not the email has an account — avoids
    // revealing which emails exist.
    msgBox.textContent = data.message || 'If an account exists for this email, a reset link has been sent.';
    msgBox.style.display = 'block';
  } catch(err){
    msgBox.textContent = 'Could not reach the server. Is the backend running?';
    msgBox.style.display = 'block';
  } finally {
    submitBtn.disabled = false;
  }
});

document.getElementById('reset-password-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errBox = document.getElementById('reset-password-error');
  const errText = document.getElementById('reset-password-error-text');
  errBox.classList.remove('show');

  const newPassword = document.getElementById('reset-new-password').value;
  const confirmPassword = document.getElementById('reset-confirm-password').value;
  if(newPassword !== confirmPassword){
    errText.textContent = 'Passwords do not match.';
    errBox.classList.add('show');
    return;
  }

  const token = new URLSearchParams(window.location.search).get('reset_token');
  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  try{
    const {ok, data} = await apiPost('/reset-password', {token, password: newPassword});
    if(!ok){
      errText.textContent = data.error || 'Could not reset password.';
      errBox.classList.add('show');
      return;
    }
    toast('Password updated — please log in.');
    // Clean the token out of the URL so a refresh doesn't reopen this form.
    window.history.replaceState({}, '', window.location.pathname);
    showAuthView('login');
  } catch(err){
    errText.textContent = 'Could not reach the server. Is the backend running?';
    errBox.classList.add('show');
  } finally {
    submitBtn.disabled = false;
  }
});
