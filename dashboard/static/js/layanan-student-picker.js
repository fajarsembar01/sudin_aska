(function () {
    const input = document.getElementById('nisn');
    if (!input) return;
    const picker = document.getElementById('student-picker');
    const panel = document.getElementById('student-panel');
    const results = document.getElementById('student-results');
    const feedback = document.getElementById('student-feedback');
    const name = document.getElementById('student_name');
    const school = document.getElementById('school_origin_id');
    let timer, controller, generation = 0, matches = [], active = -1, filled = null;
    function close() {
        panel.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant');
        active = -1;
    }
    function stop() {
        clearTimeout(timer);
        generation++;
        if (controller) controller.abort();
    }
    function selectStudent(student) {
        stop();
        input.value = student.nisn;
        name.value = student.student_name;
        school.value = student.school_origin_id ? String(student.school_origin_id) : '';
        school.dispatchEvent(new Event('student-school-selected'));
        filled = { nisn: input.value, name: name.value, school: school.value };
        feedback.textContent = 'Data ' + student.student_name + ' terisi dari catatan terakhir. ' + (school.value ? 'Sekolah asal bisa diganti jika siswa sudah pindah atau naik jenjang. Pilih sekolah yang sesuai untuk layanan ini.' : 'Pilih sekolah asal yang sesuai untuk layanan ini dari daftar.');
        close();
    }
    async function search() {
        stop();
        close();
        const term = input.value.trim();
        if (!/^[0-9]{3,10}$/.test(term)) {
            feedback.textContent = 'Ketik minimal 3 angka NISN untuk mencari siswa.';
            return;
        }
        const current = generation;
        feedback.textContent = 'Mencari siswa…';
        timer = setTimeout(async () => {
            controller = new AbortController();
            try {
                const url = new URL(input.dataset.searchUrl, location.href);
                url.searchParams.set('q', term);
                const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' }, cache: 'no-store' });
                if (!response.ok) throw new Error('Search failed');
                const data = await response.json();
                if (current !== generation || input.value.trim() !== term) return;
                matches = data.students;
                results.replaceChildren();
                matches.forEach((student, index) => {
                    const option = document.createElement('div');
                    option.id = 'student-result-' + index;
                    option.className = 'school-result';
                    option.setAttribute('role', 'option');
                    option.setAttribute('aria-selected', 'false');
                    const title = document.createElement('div');
                    title.className = 'school-result-name';
                    title.textContent = student.nisn + ' — ' + student.student_name;
                    const subtitle = document.createElement('div');
                    subtitle.className = 'school-result-meta';
                    subtitle.textContent = student.school_origin ? 'Sekolah pada catatan terakhir: ' + student.school_origin : 'Sekolah perlu dipilih kembali';
                    option.append(title, subtitle);
                    option.addEventListener('mousedown', event => event.preventDefault());
                    option.addEventListener('click', () => selectStudent(student));
                    results.append(option);
                });
                panel.hidden = !matches.length;
                input.setAttribute('aria-expanded', String(!!matches.length));
                feedback.textContent = matches.length ? 'Pilih nama siswa untuk mengisi data otomatis.' : 'Belum ada catatan dengan NISN ini. Isi nama dan sekolah asal untuk siswa baru.';
            } catch (error) {
                if (error.name !== 'AbortError' && current === generation) feedback.textContent = 'Pencarian belum tersedia. Coba lagi atau isi data siswa secara manual.';
            }
        }, 220);
    }
    input.addEventListener('input', () => {
        if (filled && input.value !== filled.nisn) {
            if (name.value === filled.name) name.value = '';
            if (school.value === filled.school) {
                school.value = '';
                school.dispatchEvent(new Event('student-school-selected'));
            }
            filled = null;
        }
        search();
    });
    input.addEventListener('focus', search);
    input.addEventListener('keydown', event => {
        if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !panel.hidden && matches.length) {
            event.preventDefault();
            active = event.key === 'ArrowDown' ? (active + 1) % matches.length : (active <= 0 ? matches.length - 1 : active - 1);
            Array.from(results.children).forEach((option, index) => {
                option.classList.toggle('is-active', index === active);
                option.setAttribute('aria-selected', String(index === active));
            });
            const option = results.children[active];
            input.setAttribute('aria-activedescendant', option.id);
            option.scrollIntoView({ block: 'nearest' });
        } else if (event.key === 'Enter' && !panel.hidden && active >= 0) {
            event.preventDefault();
            selectStudent(matches[active]);
        } else if (event.key === 'Escape' || event.key === 'Tab') { stop(); close(); }
    });
    picker.addEventListener('focusout', event => { if (!picker.contains(event.relatedTarget)) { stop(); close(); } });
    document.addEventListener('pointerdown', event => { if (!picker.contains(event.target)) { stop(); close(); } });
})();
