/* Panisara */
/* ---------------- Month calendar: shared grid, resource calendar, professor appointment calendar ---------------- */
const CAL_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const CAL_MAX_CHIPS = 2;

function calKey(date){
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}
function calDayKey(date){
  return `${calKey(date)}-${String(date.getDate()).padStart(2, '0')}`;
}
function calShift(key, delta){
  const [y, m] = key.split('-').map(Number);
  return calKey(new Date(y, m - 1 + delta, 1));
}
function calTitle(key){
  const [y, m] = key.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString([], {month: 'long', year: 'numeric'});
}

// items: [{start: Date, end: Date, ...}] -> {'2026-11-05': [item, ...]}. An item that runs past
// midnight is listed on every day it touches.
function calGroupByDay(items){
  const days = {};
  items.forEach(item => {
    const day = new Date(item.start.getFullYear(), item.start.getMonth(), item.start.getDate());
    do {
      const key = calDayKey(day);
      (days[key] = days[key] || []).push(item);
      day.setDate(day.getDate() + 1);
    } while(day < item.end);
  });
  return days;
}

function calBarButtons(key){
  return `<button class="btn" type="button" data-cal-nav="prev" aria-label="Previous month">‹</button>
    <b class="cal-title">${calTitle(key)}</b>
    <button class="btn" type="button" data-cal-nav="next" aria-label="Next month">›</button>
    <button class="btn" type="button" data-cal-nav="today">Today</button>`;
}
function calBar(key){
  return `<div class="cal-bar">${calBarButtons(key)}</div>`;
}

// chip(item) returns the little label shown inside a day cell.
function calGrid(key, byDay, selected, chip){
  const [y, m] = key.split('-').map(Number);
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7;      // weeks start on Monday
  const total = new Date(y, m, 0).getDate();
  const today = calDayKey(new Date());
  let cells = '<div class="cal-cell cal-empty"></div>'.repeat(lead);
  for(let d = 1; d <= total; d++){
    const k = `${key}-${String(d).padStart(2, '0')}`;
    const list = byDay[k] || [];
    const more = list.length > CAL_MAX_CHIPS ? `<span class="cal-more">+${list.length - CAL_MAX_CHIPS} more</span>` : '';
    cells += `<button type="button" class="cal-cell${k === today ? ' cal-today' : ''}${k === selected ? ' cal-selected' : ''}${list.length ? ' cal-has' : ''}" data-cal-day="${k}">
      <span class="cal-num">${d}</span>${list.slice(0, CAL_MAX_CHIPS).map(chip).join('')}${more}</button>`;
  }
  cells += '<div class="cal-cell cal-empty"></div>'.repeat((7 - (lead + total) % 7) % 7);
  return `<div class="cal-grid"><div class="cal-head">${CAL_DAYS.map(n => `<span>${n}</span>`).join('')}</div>
    <div class="cal-body">${cells}</div></div>`;
}

function calLegend(entries){
  return `<div class="cal-legend">${entries.map(e => `<span><i class="${e[0]}"></i>${e[1]}</span>`).join('')}</div>`;
}

function calDayTitle(dayKey){
  const [y, m, d] = dayKey.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], {weekday: 'long', day: 'numeric', month: 'long'});
}

// Moves the selected day when the month changes: today if it is in that month, otherwise nothing.
function calDefaultDay(key){
  const today = calDayKey(new Date());
  return today.startsWith(key) ? today : null;
}

function calNextMonth(key, how){
  if(how === 'prev') return calShift(key, -1);
  if(how === 'next') return calShift(key, 1);
  return calKey(new Date());
}

/* ----- Resource calendar (everyone) ----- */
const calRes = {id: null, month: calKey(new Date()), bookings: [], selected: null, wired: false};
let calPreselect = null;

const calResStatusClass = (b) => b.status === 'Pending' ? 'cal-pending' : 'cal-approved';

function calResItems(){
  return calRes.bookings.map(b => ({...b, start: new Date(b.start_time), end: new Date(b.end_time)}));
}

function calResChip(b){
  const label = isStaffRole() && b.requester_name ? b.requester_name : 'Booked';
  return `<span class="cal-chip ${calResStatusClass(b)}">${s5Time(b.start_time)} ${escapeHtml(label)}</span>`;
}

function renderResourceCalendar(){
  const byDay = calGroupByDay(calResItems());
  const list = calRes.selected ? (byDay[calRes.selected] || []) : [];
  const staff = isStaffRole();
  let detail = '<p class="note">Pick a day to see the times.</p>';
  if(calRes.selected){
    detail = `<h3 class="s5-sec">${calDayTitle(calRes.selected)}</h3>` + (list.length ? list.map(b => `
      <div class="rd-slot"><span>${s5Time(b.start_time)} – ${s5Time(b.end_time)}
          ${s5Badge(b.status === 'Pending' ? 'Pending' : 'Approved', b.status === 'Pending' ? 'b-amber' : 'b-green')}</span>
        <span>${staff ? `${escapeHtml(b.requester_name)}${b.purpose ? ' · ' + escapeHtml(b.purpose) : ''}` : 'Booked'}</span></div>`).join('')
      : '<p class="note">Nothing booked this day.</p>');
  }
  document.getElementById('cal-bar').innerHTML = calBarButtons(calRes.month);
  document.getElementById('cal-content').innerHTML = `
    ${calLegend([['cal-approved', 'Approved (taken)'], ['cal-pending', 'Pending (also blocks the slot)']])}
    <div class="cal-layout">
      <div class="cal-main">${calGrid(calRes.month, byDay, calRes.selected, calResChip)}</div>
      <aside class="cal-detail" aria-label="Selected day">${detail}</aside>
    </div>`;
}

async function loadResourceCalendar(){
  const box = document.getElementById('cal-content');
  if(!calRes.id){
    document.getElementById('cal-bar').innerHTML = '';
    box.innerHTML = '<p class="note">There are no resources yet.</p>';
    return true;
  }
  const {ok, data} = await apiAuthGet(`/api/calendar/resource/${calRes.id}?month=${calRes.month}`);
  if(!ok){ box.innerHTML = `<p class="note">${escapeHtml(data.error || 'Could not load the calendar')}</p>`; return false; }
  calRes.bookings = data.bookings;
  renderResourceCalendar();
  return true;
}

async function openCalendar(){
  const select = document.getElementById('cal-resource');
  const {ok, data} = await apiAuthGet('/api/resources');
  const resources = ok ? data.resources.filter(r => !r.is_archived) : [];
  select.innerHTML = resources.map(r => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join('');
  const wanted = calPreselect || calRes.id;
  calPreselect = null;
  calRes.id = resources.some(r => r.id === wanted) ? wanted : (resources[0] ? resources[0].id : null);
  if(calRes.id) select.value = String(calRes.id);
  calRes.month = calKey(new Date());
  calRes.selected = calDefaultDay(calRes.month);
  if(!calRes.wired){
    calRes.wired = true;
    select.addEventListener('change', () => { calRes.id = Number(select.value); calRes.selected = null; loadResourceCalendar(); });
    document.getElementById('view-calendar').addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if(!btn) return;
      if(btn.dataset.calNav){
        calRes.month = calNextMonth(calRes.month, btn.dataset.calNav);
        calRes.selected = calDefaultDay(calRes.month);
        loadResourceCalendar();
      } else if(btn.dataset.calDay){
        calRes.selected = btn.dataset.calDay;
        renderResourceCalendar();
      }
    });
    setupRefreshButton('btn-refresh-calendar', () => loadResourceCalendar());
  }
  loadResourceCalendar();
}

// Used by the resource detail card: jump to the calendar with that resource chosen.
function showCalendarFor(resourceId){
  calPreselect = resourceId;
  document.querySelector('.nav-item[data-view="calendar"]').click();
}

/* ----- Professor appointment calendar (professors only) ----- */
const calProf = {month: calKey(new Date()), appointments: [], selected: null, wired: false};
let apptView = 'list';

function calProfItems(){
  return calProf.appointments.map(a => ({...a, start: new Date(a.start_time), end: new Date(a.end_time)}));
}

const calProfClass = (a) => a.status === 'Pending' ? 'cal-pending' : 'cal-accepted';

function calProfChip(a){
  return `<span class="cal-chip ${calProfClass(a)}">${s5Time(a.start_time)} ${escapeHtml(a.student_name)}</span>`;
}

function renderApptTabs(){
  const tabs = document.getElementById('appt-tabs');
  tabs.hidden = currentRole !== 'professor';
  if(tabs.hidden) return;
  tabs.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.apptView === apptView));
  if(!tabs.dataset.wired){
    tabs.dataset.wired = '1';
    tabs.addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if(!btn || btn.dataset.apptView === apptView) return;
      apptView = btn.dataset.apptView;
      loadAppointments();
    });
  }
}

function calProfCard(a){
  const waiting = a.status === 'Pending';
  return `<div class="appt-item" data-st="${a.status}">
    <div class="appt-row"><b>${escapeHtml(a.topic)}</b>${s5Badge(waiting ? 'Waiting for your answer' : 'Accepted', waiting ? 'b-amber' : 'b-green')}</div>
    <p><b>${escapeHtml(a.student_name)}</b> · ${s5Time(a.start_time)} – ${s5Time(a.end_time)}</p>
    ${a.details ? `<p>${escapeHtml(a.details)}</p>` : ''}
    ${waiting ? `<div class="appt-acts"><button class="btn no" type="button" data-appt-decline="${a.id}">Decline</button>
      <button class="btn ok" type="button" data-appt-accept="${a.id}">Accept</button></div>` : ''}
  </div>`;
}

function renderProfessorCalendar(){
  const byDay = calGroupByDay(calProfItems());
  const list = calProf.selected ? (byDay[calProf.selected] || []) : [];
  let detail = '<p class="note">Pick a day to see the appointments.</p>';
  if(calProf.selected){
    detail = `<h3 class="s5-sec">${calDayTitle(calProf.selected)}</h3>` +
      (list.length ? list.map(calProfCard).join('') : '<p class="note">No appointments this day.</p>');
  }
  document.getElementById('appt-content').innerHTML = `
    ${calBar(calProf.month)}
    ${calLegend([['cal-accepted', 'Accepted'], ['cal-pending', 'Waiting for your answer']])}
    ${calGrid(calProf.month, byDay, calProf.selected, calProfChip)}
    <div class="cal-detail">${detail}</div>`;
}

async function loadProfessorCalendar(){
  const box = document.getElementById('appt-content');
  const {ok, data} = await apiAuthGet(`/api/calendar/appointments?month=${calProf.month}`);
  if(!ok){ box.innerHTML = `<p class="note">${escapeHtml(data.error || 'Could not load the calendar')}</p>`; return false; }
  calProf.appointments = data.appointments;
  if(!calProf.wired){
    calProf.wired = true;
    box.addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if(!btn || apptView !== 'calendar') return;
      if(btn.dataset.calNav){
        calProf.month = calNextMonth(calProf.month, btn.dataset.calNav);
        calProf.selected = calDefaultDay(calProf.month);
        loadProfessorCalendar();
      } else if(btn.dataset.calDay){
        calProf.selected = btn.dataset.calDay;
        renderProfessorCalendar();
      }
    });
  }
  renderProfessorCalendar();
  return true;
}
