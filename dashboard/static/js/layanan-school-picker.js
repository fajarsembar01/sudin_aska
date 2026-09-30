/* Accessible school combobox; the original select remains the submitted value. */
(function () {
    const select = document.getElementById('school_origin_id');
    const input = document.getElementById('school-origin-search');
    if (!select || !input) return;
    const picker = document.getElementById('school-picker');
    const panel = document.getElementById('school-origin-panel');
    const results = document.getElementById('school-origin-results');
    const count = document.getElementById('school-origin-count');
    const empty = document.getElementById('school-origin-empty');
    const clear = document.getElementById('school-origin-clear');
    const feedback = document.getElementById('school-origin-feedback');
    const schools = Array.from(select.options).filter(option => option.value).map(option => ({
        id: option.value, name: option.dataset.name, npsn: option.dataset.npsn,
        active: option.dataset.active === 'true'
    }));
    let matches = [], active = -1;
    const normalize = value => value.toLocaleLowerCase('id').replace(/\s+/g, ' ').trim();
    function validate() {
        input.setCustomValidity(select.value ? '' : 'Pilih sekolah dari hasil pencarian.');
        clear.hidden = !input.value;
    }
    function close() {
        panel.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
        active = -1;
    }
    function choose(school) {
        select.value = school.id;
        input.value = school.name;
        feedback.textContent = 'Sekolah dipilih · NPSN ' + school.npsn + (school.active ? '' : ' · Nonaktif');
        input.removeAttribute('aria-invalid');
        validate();
        close();
        select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function highlight(index) {
        active = index;
        Array.from(results.children).forEach((option, i) => option.classList.toggle('is-active', i === active));
        const option = results.children[active];
        if (option) {
            input.setAttribute('aria-activedescendant', option.id);
            option.scrollIntoView({ block: 'nearest' });
        } else input.removeAttribute('aria-activedescendant');
    }
    function show() {
        const tokens = normalize(input.value).split(' ').filter(Boolean);
        const found = schools.filter(school => tokens.every(token => normalize(school.name + ' ' + school.npsn).includes(token)));
        matches = found.slice(0, 15);
        active = -1;
        input.removeAttribute('aria-activedescendant');
        results.replaceChildren();
        matches.forEach((school, index) => {
            const option = document.createElement('div');
            option.id = 'school-result-' + school.id;
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
            option.addEventListener('click', () => { choose(school); input.focus(); close(); });
            results.append(option);
        });
        count.textContent = found.length > 15 ? 'Menampilkan 15 sekolah. Ketik lebih lengkap untuk mempersempit hasil.' : found.length + ' sekolah ditemukan';
        empty.hidden = found.length > 0;
        panel.hidden = false;
        input.setAttribute('aria-expanded', 'true');
    }
    input.addEventListener('focus', show);
    input.addEventListener('input', () => {
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
            if (matches.length) highlight(event.key === 'ArrowDown' ? (active + 1) % matches.length : (active <= 0 ? matches.length - 1 : active - 1));
        } else if (event.key === 'Enter' && !panel.hidden && active >= 0) {
            event.preventDefault();
            choose(matches[active]);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            close();
        } else if (event.key === 'Tab') close();
    });
    input.addEventListener('invalid', () => {
        input.setAttribute('aria-invalid', 'true');
        feedback.textContent = 'Pilih sekolah dari hasil pencarian sebelum menyimpan.';
    });
    picker.addEventListener('focusout', event => { if (!picker.contains(event.relatedTarget)) close(); });
    document.addEventListener('pointerdown', event => { if (!picker.contains(event.target)) close(); });
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
    select.addEventListener('student-school-selected', () => {
        const school = schools.find(item => item.id === select.value);
        if (school) choose(school);
        else {
            input.value = '';
            select.value = '';
            feedback.textContent = '';
            validate();
            close();
        }
    });
    if (initial) choose(initial);
    select.hidden = true;
    select.required = false;
    document.getElementById('school-origin-label').htmlFor = input.id;
    document.getElementById('school-search-control').hidden = false;
    input.required = true;
    validate();
})();
