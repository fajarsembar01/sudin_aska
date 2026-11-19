/* Keep room search available while scrolling the mobile assessment form. */
document.addEventListener('DOMContentLoaded', function () {
  const main = document.getElementById('roomSearchAssessment');
  const anchor = document.getElementById('assessmentSearchAnchor');
  const toggle = document.getElementById('assessmentSearchFloating');
  const panel = document.getElementById('assessmentSearchPanel');
  const input = document.getElementById('assessmentSearchMobileInput');
  const clear = document.getElementById('assessmentSearchClear');
  const status = document.getElementById('assessmentSearchCount');
  const empty = document.getElementById('assessmentSearchEmpty');
  const results = document.getElementById('roomAccordion');
  if (!main || !anchor || !toggle || !panel || !results) return;
  const mobile = window.matchMedia('(max-width: 767.98px)');
  const rooms = Array.from(results.querySelectorAll('.room-item'));
  let open = false;
  let scheduled = false;

  function updateVisibility() {
    scheduled = false;
    if (!mobile.matches) close(false);
    toggle.hidden = !mobile.matches || (!open && anchor.getBoundingClientRect().bottom > 112);
  }
  function scheduleVisibility() {
    if (!scheduled) { scheduled = true; window.requestAnimationFrame(updateVisibility); }
  }
  function updateSearch() {
    input.value = main.value;
    const query = main.value.toLowerCase().trim();
    const count = rooms.filter(room => query.length < 2 || (room.dataset.roomName || '').includes(query)).length;
    status.textContent = query.length === 1 ? 'Ketik minimal 2 karakter' : `${count} ruangan ditemukan`;
    empty.hidden = count > 0;
    clear.disabled = !main.value;
    toggle.classList.toggle('has-query', query.length > 0);
  }
  function close(focusToggle) {
    open = false;
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    input.blur();
    if (focusToggle) toggle.focus({preventScroll: true});
  }
  function clearSearch() {
    main.value = '';
    main.dispatchEvent(new Event('input', {bubbles: true}));
  }
  toggle.addEventListener('click', function () {
    if (open) { close(true); updateVisibility(); return; }
    open = true;
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    updateSearch();
    input.focus({preventScroll: true});
  });
  input.addEventListener('input', function () {
    main.value = input.value;
    main.dispatchEvent(new Event('input', {bubbles: true}));
  });
  main.addEventListener('input', updateSearch);
  clear.addEventListener('click', function () { clearSearch(); input.focus({preventScroll: true}); });
  document.getElementById('assessmentSearchReset').addEventListener('click', clearSearch);
  document.getElementById('assessmentSearchClose').addEventListener('click', function () { close(true); updateVisibility(); });
  panel.addEventListener('submit', function (event) {
    event.preventDefault();
    close(false);
    (empty.hidden ? results : empty).scrollIntoView({behavior: 'smooth', block: 'start'});
    scheduleVisibility();
  });
  panel.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { close(true); updateVisibility(); }
  });
  window.addEventListener('scroll', scheduleVisibility, {passive: true});
  window.addEventListener('resize', scheduleVisibility, {passive: true});
  mobile.addEventListener('change', updateVisibility);
  document.addEventListener('show.bs.modal', function () { close(false); });
  updateSearch();
  updateVisibility();
});
