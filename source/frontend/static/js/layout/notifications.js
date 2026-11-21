/*  Notifications (the bell)  */
let notifTimer = null;

function setBellBadge(n){
  const b = document.getElementById('bell-badge');
  b.textContent = n > 99 ? '99+' : String(n);
  b.classList.toggle('show', n > 0);
}
async function refreshUnread(){
  const {ok, data} = await apiAuthGet('/api/notifications/unread-count');
  if(ok) setBellBadge(data.unread);
}
function startNotifications(){
  clearInterval(notifTimer);
  refreshUnread();
  // A cheap count every 45 s while the tab is visible - no WebSocket needed for a lab this size.
  notifTimer = setInterval(() => { if(!document.hidden) refreshUnread(); }, 45000);
}
let bellItems = [];
let bellHasMore = false;
function renderBell(){
  const box = document.getElementById('bell-list');
  box.innerHTML = (bellItems.length ? bellItems.map(n => `
    <button type="button" class="bell-item-row ${n.is_read ? '' : 'unread'}" data-nid="${n.id}" data-view="${escapeHtml(n.view)}">
      <b>${escapeHtml(n.title)}</b><span>${escapeHtml(n.body)}</span><small>${s5When(n.created_at)}</small>
    </button>`).join('') : '<div class="bell-empty">No notifications yet.</div>')
    + (bellHasMore ? '<button type="button" class="btn" id="bell-more" style="margin:10px 14px;">Load more</button>' : '');
}
// Is there a menu entry this account can actually open? (Hidden entries are display:none.)
function viewAvailable(key){
  const btn = document.querySelector(`.nav-item[data-view="${key}"]`);
  return !!btn && getComputedStyle(btn).display !== 'none';
}
function placeBell(){
  const menu = document.getElementById('bell-menu');
  const r = document.getElementById('bell-btn').getBoundingClientRect();
  const w = menu.offsetWidth, h = menu.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
  let left, top;
  if(r.left + r.width / 2 < vw / 3){
    // The bell lives in the side rail: open the menu beside the rail, level with the bell.
    // 262 = the rail when expanded (236 px wide + 14 px margin) + a gap: it grows while the pointer
    // is on it, so measuring the bell mid-animation would put the menu on top of the rail.
    left = Math.min(Math.max(r.right + 12, 262), vw - w - 12);
    top = Math.min(r.top, vh - h - 12);
  } else {
    // The bell is in a top bar: open the menu underneath it.
    left = Math.min(r.right - w, vw - w - 12);
    top = r.bottom + 8;
  }
  menu.style.left = Math.max(12, left) + 'px';
  menu.style.top = Math.max(12, Math.min(top, vh - h - 12)) + 'px';
  menu.style.bottom = 'auto';
}
async function toggleBell(){
  const menu = document.getElementById('bell-menu');
  if(menu.classList.contains('open')){ menu.classList.remove('open'); return; }
  const {ok, data} = await apiAuthGet('/api/notifications');
  if(!ok){ toast(data.error || 'Could not load notifications'); return; }
  bellItems = data.notifications;
  bellHasMore = !!data.has_more;
  renderBell();
  setBellBadge(data.unread);
  menu.classList.add('open');
  placeBell();
}
async function loadMoreBell(btn){
  if(!bellItems.length) return;
  btn.disabled = true;
  const {ok, data} = await apiAuthGet('/api/notifications?before=' + bellItems[bellItems.length - 1].id);
  if(!ok){ btn.disabled = false; toast(data.error || 'Could not load more'); return; }
  bellItems = bellItems.concat(data.notifications);
  bellHasMore = !!data.has_more;
  const list = document.getElementById('bell-list');
  const top = list.scrollTop;
  renderBell();
  list.scrollTop = top;
  placeBell();
}
document.getElementById('bell-btn').addEventListener('click', (e) => { e.stopPropagation(); toggleBell(); });
document.getElementById('bell-menu').addEventListener('click', async (e) => {
  e.stopPropagation();
  const more = e.target.closest('#bell-more');
  if(more){ loadMoreBell(more); return; }
  const row = e.target.closest('[data-nid]');
  if(!row) return;
  document.getElementById('bell-menu').classList.remove('open');
  apiAuthSend('POST', `/api/notifications/${row.dataset.nid}/read`).then(refreshUnread);
  if(!viewAvailable(row.dataset.view)){
    toast('That page is not available for your account.');
    return;
  }
  goView(row.dataset.view);   // straight to the page it is about
});
document.getElementById('bell-readall').addEventListener('click', async (e) => {
  e.stopPropagation();
  await apiAuthSend('POST', '/api/notifications/read-all');
  bellItems.forEach(n => { n.is_read = true; });
  document.querySelectorAll('#bell-list .unread').forEach(el => el.classList.remove('unread'));
  setBellBadge(0);
});
document.addEventListener('click', () => document.getElementById('bell-menu').classList.remove('open'));
