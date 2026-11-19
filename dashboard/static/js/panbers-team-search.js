(function () {
  'use strict';
  const input = document.getElementById('teamSearch');
  if (!input) return;
  const clear = document.getElementById('teamSearchClear');
  const summary = document.getElementById('teamSearchSummary');
  const groups = [
    { root: 'teamAssignments', empty: 'teamAssignmentsEmpty' },
    { root: 'teamHistory', empty: 'teamHistoryEmpty' }
  ].map(function (group) {
    return {
      empty: document.getElementById(group.empty),
      items: Array.from(document.getElementById(group.root).querySelectorAll('[data-team-search]'))
    };
  });
  function normalize(value) {
    return value.normalize('NFKC').toLocaleLowerCase('id').replace(/\s+/g, ' ').trim();
  }
  function filter() {
    const terms = normalize(input.value).split(' ').filter(Boolean);
    const counts = groups.map(function (group) {
      let count = 0;
      group.items.forEach(function (item) {
        const content = normalize(item.dataset.teamSearch);
        const matches = terms.every(function (term) { return content.includes(term); });
        // Bootstrap's d-flex overrides the native hidden attribute on history links.
        item.classList.toggle('d-none', !matches);
        if (matches) count += 1;
      });
      group.empty.hidden = !terms.length || !group.items.length || count > 0;
      return count;
    });
    clear.hidden = !input.value;
    summary.hidden = !terms.length;
    summary.textContent = counts[0] + ' sekolah penugasan · ' + counts[1] + ' hasil tim ditemukan';
  }
  input.addEventListener('input', filter);
  clear.addEventListener('click', function () {
    input.value = '';
    filter();
    input.focus();
  });
  filter();
})();
