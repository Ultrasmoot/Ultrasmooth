/* Check in / Check out */
const CI_RES_BADGE = {'Available':'b-green', 'In Use':'b-amber', 'Maintenance':'b-rust'};
let checkinData = {in_use: [], ready: [], done: []};
let ciFlow = null; 
let ciTimer = null;

function ciTime(iso){
  return new Date(iso).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', hour12:false});
}
function ciMask(email){
  const [name, domain] = String(email || '').split('@');
  return domain ? `${name.slice(0, 1)}*****@${domain}` : '*****';
}
function ciBooking(id){
  return [...checkinData.ready, ...checkinData.in_use].find(b => b.id === id);
}

function ciCard(b, kind){
  const d = new Date(b.start_time);
  const badge = `<span class="badge ${CI_RES_BADGE[b.resource_status] || ''}">${escapeHtml(b.resource_status)}</span>`;
  let foot = '', actions = '';
  if(kind === 'ready'){
    foot = `<span>${escapeHtml(b.block_reason || 'Ready to check in.')}</span>`;
    actions = `<button class="req-btn approve" type="button" data-ci="in" ${b.can_check_in ? '' : 'disabled'}>Check in</button>`;
  } else if(kind === 'in_use'){
    foot = `<span>Checked in at ${ciTime(b.checked_in_at)} · booked until ${ciTime(b.end_time)}</span>`;
    actions = `<button class="req-btn approve" type="button" data-ci="out">Check out</button>`;
  } else {
    foot = `<span>${ciTime(b.checked_in_at)} → ${ciTime(b.checked_out_at)}</span>`;
  }
  return `
    <article class="req" data-id="${b.id}">
      <div class="req-row">
        <div class="leaf" aria-hidden="true">
          <span class="leaf-mon">${d.toLocaleString('en-US', {month:'short'})}</span>
          <span class="leaf-day">${d.getDate()}</span>
          <span class="leaf-wd">${d.toLocaleString('en-US', {weekday:'short'})}</span>
        </div>
        <div class="req-body">
          <div class="req-title"><h3>${escapeHtml(b.resource_name)}</h3>${kind === 'done' ? '' : badge}</div>
          <p class="req-purpose"><b>${escapeHtml(b.resource_code)}</b>${ciTime(b.start_time)}–${ciTime(b.end_time)} · ${escapeHtml(b.purpose)}</p>
          <div class="req-foot">${foot}</div>
        </div>
        ${actions ? `<div class="req-actions">${actions}</div>` : ''}
      </div>
    </article>`;
}

function renderCheckin(){
  const sec = (title, list, kind, emptyText) => `
    <h3 class="ci-h">${title}</h3>
    ${list.length ? `<div class="req-list">${list.map(b => ciCard(b, kind)).join('')}</div>` : `<p class="note">${emptyText}</p>`}`;
  document.getElementById('ci-content').innerHTML =
    sec('Currently in use by you', checkinData.in_use, 'in_use', 'You are not using any resource right now.') +
    sec('Approved bookings', checkinData.ready, 'ready', 'No upcoming approved bookings. Book a resource from the Resources page.') +
    sec('Recently completed', checkinData.done, 'done', 'Nothing yet.');
}

async function loadCheckin(silent = false){
  const {ok, data} = await apiAuthGet('/api/checkin/mine');
  if(!ok){
    if(!silent) toast(data.error || 'Could not load your bookings');
    return false;
  }
  checkinData = data;
  renderCheckin();
  return true;
}

document.getElementById('ci-content').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-ci]');
  if(!btn) return;
  const id = Number(btn.closest('.req').dataset.id);
  if(btn.dataset.ci === 'in') openCheckinModal(id);
  if(btn.dataset.ci === 'out') openCheckoutModal(id);
});

function ciShowError(msg){
  const box = document.getElementById('ci-error');
  document.getElementById('ci-error-text').textContent = msg;
  box.classList.add('show');
}
function ciClearError(){
  document.getElementById('ci-error')?.classList.remove('show');
}
const ciErrorBox = '<div id="ci-error" class="login-error"><span>⚠</span><span id="ci-error-text"></span></div>';

function openCheckinModal(id){
  ciFlow = {id, step: 1};
  renderCheckinModal();
  document.getElementById('modal-backdrop').classList.add('open');
}

function renderCheckinModal(){
  const b = ciBooking(ciFlow.id);
  const box = document.getElementById('modal-box');
  if(!b){ closeModal(); return; }

  if(ciFlow.step === 1){
    box.innerHTML = `
      <h3>Check in to ${escapeHtml(b.resource_name)}?</h3>
      <p class="note" style="margin:0;">To confirm it is you, we will e-mail a 6-digit code to the address you registered with.</p>
      <div class="ci-box"><b>${escapeHtml(b.resource_code)}</b><br>Booking: ${ciTime(b.start_time)}–${ciTime(b.end_time)}<br>Send code to: <b>${escapeHtml(ciMask(currentUser?.email))}</b></div>
      ${ciErrorBox}
      <div class="ci-foot"><button class="btn no" type="button" id="ci-cancel">Cancel</button><button class="btn ok" type="button" id="ci-send">Send code</button></div>`;
    document.getElementById('ci-cancel').addEventListener('click', closeModal);
    document.getElementById('ci-send').addEventListener('click', ciSendCode);
  } else if(ciFlow.step === 2){
    box.innerHTML = `
      <h3>Enter your code</h3>
      <p class="note" style="margin:0 0 12px;">We sent a 6-digit code to <b>${escapeHtml(ciFlow.hint)}</b>. Enter it below.</p>
      <input class="ci-otp" id="ci-otp" inputmode="numeric" maxlength="6" placeholder="••••••" autocomplete="one-time-code" aria-label="6-digit code">
      ${ciErrorBox}
      <p class="note" id="ci-cd" style="margin:10px 0 0;"></p>
      <div class="ci-foot">
        <button class="ci-link" type="button" id="ci-resend" disabled>Resend code</button>
        <span><button class="btn no" type="button" id="ci-cancel">Cancel</button> <button class="btn ok" type="button" id="ci-verify">Verify &amp; check in</button></span>
      </div>`;
    const input = document.getElementById('ci-otp');
    input.addEventListener('input', () => { input.value = input.value.replace(/\D/g, ''); });
    input.addEventListener('keydown', (e) => { if(e.key === 'Enter') ciVerify(); });
    document.getElementById('ci-cancel').addEventListener('click', closeModal);
    document.getElementById('ci-verify').addEventListener('click', ciVerify);
    document.getElementById('ci-resend').addEventListener('click', ciSendCode);
    input.focus();
    ciStartTimer();
  } else {
    box.innerHTML = `
      <h3>Checked in</h3>
      <div class="ci-ok">✓ ${escapeHtml(b.resource_name)} is now <b>In Use</b> · ${ciTime(ciFlow.checkedInAt)}</div>
      <p class="note" style="margin:0;">Remember to check out when you are finished.</p>
      <div class="ci-foot"><span></span><button class="btn ok" type="button" id="ci-done">Done</button></div>`;
    document.getElementById('ci-done').addEventListener('click', closeModal);
  }
}

function ciStartTimer(){
  clearInterval(ciTimer);
  const tick = () => {
    const cd = document.getElementById('ci-cd');
    const resend = document.getElementById('ci-resend');
    if(!cd || !ciFlow || ciFlow.step !== 2){ clearInterval(ciTimer); return; }
    const left = Math.max(0, Math.ceil((ciFlow.expiresAt - Date.now()) / 1000));
    cd.textContent = left > 0
      ? `Code expires in ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} · attempts left: ${ciFlow.attemptsLeft}`
      : 'This code has expired — request a new one.';
    const wait = Math.ceil((ciFlow.resendAt - Date.now()) / 1000);
    resend.disabled = wait > 0;
    resend.textContent = wait > 0 ? `Resend in ${wait}s` : 'Resend code';
    document.getElementById('ci-verify').disabled = ciFlow.locked || left <= 0;
  };
  tick();
  ciTimer = setInterval(tick, 1000);
}

async function ciSendCode(){
  ciClearError();
  const btn = document.getElementById('ci-send') || document.getElementById('ci-resend');
  if(btn) btn.disabled = true;
  const {ok, status, data} = await apiAuthSend('POST', `/api/checkin/${ciFlow.id}/code`);
  if(!ok){
    if(status === 429 && ciFlow.step === 2){
      ciFlow.resendAt = Date.now() + (data.retry_after || 30) * 1000;
      ciShowError(data.error);
    } else if(status === 400 && !/wait/i.test(data.error || '')){
      // The booking itself can no longer be checked in to 
      closeModal();
      toast(data.error || 'Could not send the code');
      loadCheckin(true);
    } else {
      ciShowError(data.error || 'Could not send the code. Please try again.');
      if(btn) btn.disabled = false;
    }
    return;
  }
  ciFlow.step = 2;
  ciFlow.hint = data.email_hint;
  ciFlow.expiresAt = Date.now() + data.expires_in * 1000;
  ciFlow.resendAt = Date.now() + data.resend_in * 1000;
  ciFlow.attemptsLeft = data.max_attempts;
  ciFlow.locked = false;
  renderCheckinModal();
  toast(`Code sent to ${data.email_hint}`);
}

async function ciVerify(){
  const input = document.getElementById('ci-otp');
  ciClearError();
  const code = input.value.trim();
  if(!/^\d{6}$/.test(code)){ ciShowError('Please enter the 6-digit code.'); return; }
  const {ok, data} = await apiAuthSend('POST', `/api/checkin/${ciFlow.id}/verify`, {code});
  if(!ok){
    if(data.attempts_left !== undefined){
      ciFlow.attemptsLeft = data.attempts_left;
      ciFlow.locked = data.attempts_left === 0;
      ciShowError(data.error);
    } else if(/expired|No active code|6-digit/i.test(data.error || '')){
      ciShowError(data.error);
    } else {
      closeModal();
      toast('Check-in failed: ' + (data.error || 'please try again'));
      loadCheckin(true);
    }
    return;
  }
  clearInterval(ciTimer);
  ciFlow.step = 3;
  ciFlow.checkedInAt = data.booking.checked_in_at;
  renderCheckinModal();
  loadCheckin(true);
}

function openCheckoutModal(id){
  const b = ciBooking(id);
  if(!b) return;
  document.getElementById('modal-box').innerHTML = `
    <h3>Check out of ${escapeHtml(b.resource_name)}?</h3>
    <p class="note" style="margin:0;">The resource will become Available again so others can use it.</p>
    <div class="ci-foot"><button class="btn no" type="button" id="ci-cancel">Go back</button><button class="btn ok" type="button" id="ci-out">Yes, check out</button></div>`;
  document.getElementById('modal-backdrop').classList.add('open');
  document.getElementById('ci-cancel').addEventListener('click', closeModal);
  document.getElementById('ci-out').addEventListener('click', async (e) => {
    e.target.disabled = true;
    const {ok, data} = await apiAuthSend('POST', `/api/checkin/${id}/checkout`);
    closeModal();
    if(!ok){ toast(data.error || 'Could not check out'); }
    else toast(data.booking.resource_status === 'Maintenance'
      ? 'Checked out — the resource stays in Maintenance'
      : `Checked out — ${b.resource_name} is Available`);
    loadCheckin(true);
  });
}
