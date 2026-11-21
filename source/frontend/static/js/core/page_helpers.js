// Shared little helpers for the new pages.
function s5When(iso){
  return new Date(iso).toLocaleString([], {weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', hour12:false});
}
function s5Time(iso){
  return new Date(iso).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', hour12:false});
}
const S5_ICON_PERSON = (c) => `<svg viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" fill="${c}"/><circle cx="24" cy="19" r="8" fill="#fff" opacity=".92"/><path d="M8 48c2-11 10-15 16-15s14 4 16 15z" fill="#fff" opacity=".92"/></svg>`;
const S5_COLORS = ['#2C5F8A', '#A03B2A', '#2F6F4F', '#95651C', '#6B4C9A', '#1F7A86'];
// No photo yet (uploads arrive with User Management): a coloured placeholder per professor.
const profAvatar = (id, cls = '') => `<div class="prof-av ${cls}">${S5_ICON_PERSON(S5_COLORS[id % S5_COLORS.length])}</div>`;
const s5Badge = (text, cls) => `<span class="badge ${cls || 'b-faint'}">${escapeHtml(text)}</span>`;
