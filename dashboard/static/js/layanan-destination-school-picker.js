/* School destination picker with database and manual entry modes. */
(function () {
    const select = document.getElementById('school_destination_id');
    const input = document.getElementById('school-destination-search');
    const manualInput = document.getElementById('school_destination_manual');
    const databaseMode = document.getElementById('destination-mode-database');
    const manualMode = document.getElementById('destination-mode-manual');
    const databaseField = document.getElementById('destination-database-field');
    const manualField = document.getElementById('destination-manual-field');
    const serviceType = document.getElementById('service_type');
    if (!select || !input || !manualInput || !databaseMode || !manualMode) return;

    const picker = document.getElementById('destination-school-picker');
    const panel = document.getElementById('school-destination-panel');
    const results = document.getElementById('school-destination-results');
    const count = document.getElementById('school-destination-count');
    const empty = document.getElementById('school-destination-empty');
    const clear = document.getElementById('school-destination-clear');
    const feedback = document.getElementById('school-destination-feedback');
    const searchControl = document.getElementById('school-destination-search-control');
    const label = document.getElementById('school-destination-label');
    const schools = Array.from(select.options).filter(option => option.value).map(option => ({
        id: option.value,
        name: option.dataset.name,
        npsn: option.dataset.npsn,
        active: option.dataset.active === 'true'
    }));
    let matches = [];
    let activeIndex = -1;

    const normalize = value => value.toLocaleLowerCase('id').replace(/\s+/g, ' ').trim();
    const isMutation = () => serviceType && serviceType.value === 'mutasi';

    function close() {
        panel.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
        activeIndex = -1;
    }

    function validate() {
        const needsDatabaseSchool = isMutation() && databaseMode.checked;
        input.required = needsDatabaseSchool;
        input.setCustomValidity(needsDatabaseSchool && !select.value
            ? 'Pilih sekolah tujuan dari hasil pencarian.' : '');
        clear.hidden = !input.value;
    }

    function choose(school) {
        select.value = school.id;
        input.value = school.name;
        feedback.textContent = 'Sekolah dipilih · NPSN ' + school.npsn
            + (school.active ? '' : ' · Nonaktif');
        input.removeAttribute('aria-invalid');
        validate();
        close();
    }

    function highlight(index) {
        activeIndex = index;
        Array.from(results.children).forEach((option, itemIndex) => {
            option.classList.toggle('is-active', itemIndex === activeIndex);
        });
        const option = results.children[activeIndex];
        if (option) {
            input.setAttribute('aria-activedescendant', option.id);
            option.scrollIntoView({ block: 'nearest' });
        }
    }

    function show() {
        if (!databaseMode.checked || !isMutation()) return;
        const tokens = normalize(input.value).split(' ').filter(Boolean);
        const found = schools.filter(school => tokens.every(token =>
            normalize(school.name + ' ' + school.npsn).includes(token)));
        matches = found.slice(0, 15);
        activeIndex = -1;
        results.replaceChildren();
        matches.forEach(school => {
            const option = document.createElement('div');
            option.id = 'school-destination-result-' + school.id;
            option.className = 'school-result';
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', String(select.value === school.id));
            const name = document.createElement('div');
            name.className = 'school-result-name';
            name.textContent = school.name;
            const meta = document.createElement('div');
            meta.className = 'school-result-meta';
            meta.textContent = 'NPSN ' + school.npsn + (school.active ? '' : ' · Nonaktif');
            option.append(name, meta);
            option.addEventListener('mousedown', event => event.preventDefault());
            option.addEventListener('click', () => {
                choose(school);
                input.focus();
            });
            results.append(option);
        });
        count.textContent = found.length > 15
            ? 'Menampilkan 15 sekolah. Ketik lebih lengkap untuk mempersempit hasil.'
            : found.length + ' sekolah ditemukan';
        empty.hidden = found.length > 0;
        panel.hidden = false;
        input.setAttribute('aria-expanded', 'true');
    }

    function syncMode() {
        const useDatabase = databaseMode.checked;
        const active = isMutation();
        databaseField.hidden = !useDatabase;
        manualField.hidden = useDatabase;
        select.disabled = !active || !useDatabase;
        input.disabled = !active || !useDatabase;
        manualInput.disabled = !active || useDatabase;
        manualInput.required = active && !useDatabase;
        if (!useDatabase) close();
        validate();
    }

    databaseMode.addEventListener('change', syncMode);
    manualMode.addEventListener('change', syncMode);
    serviceType.addEventListener('change', syncMode);
    document.addEventListener('layanan-mutasi-toggle', syncMode);
    input.addEventListener('focus', show);
    input.addEventListener('input', function () {
        select.value = '';
        feedback.textContent = '';
        input.removeAttribute('aria-invalid');
        validate();
        show();
    });
    input.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (panel.hidden) show();
            if (matches.length) {
                highlight(event.key === 'ArrowDown'
                    ? (activeIndex + 1) % matches.length
                    : (activeIndex <= 0 ? matches.length - 1 : activeIndex - 1));
            }
        } else if (event.key === 'Enter' && !panel.hidden && activeIndex >= 0) {
            event.preventDefault();
            choose(matches[activeIndex]);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            close();
        } else if (event.key === 'Tab') {
            close();
        }
    });
    input.addEventListener('invalid', () => {
        input.setAttribute('aria-invalid', 'true');
        feedback.textContent = 'Pilih sekolah tujuan dari hasil pencarian.';
    });
    picker.addEventListener('focusout', event => {
        if (!picker.contains(event.relatedTarget)) close();
    });
    document.addEventListener('pointerdown', event => {
        if (!picker.contains(event.target)) close();
    });
    clear.addEventListener('click', () => {
        input.value = '';
        select.value = '';
        feedback.textContent = '';
        input.removeAttribute('aria-invalid');
        validate();
        input.focus();
        show();
    });

    const initial = schools.find(school => school.id === select.value);
    if (initial) choose(initial);
    select.hidden = true;
    searchControl.hidden = false;
    label.htmlFor = input.id;
    syncMode();
})();
