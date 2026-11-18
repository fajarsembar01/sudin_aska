(() => {
    'use strict';
    const modal = document.getElementById('reportNotesModal');
    if (!modal) return;
    const el = id => document.getElementById('reportNotes' + id);
    const editor = el('Editor'), status = el('Status');
    let base = null, saving = false, loading = false, open = false, timer, debounce;
    let conflict = null, historyBefore = null, historyLoading = false, blocked = false;
    const canEdit = modal.dataset.canEdit === 'true';
    const autosaveDelay = 60000;
    let pendingSince = null;
    const dirty = () => base !== null && editor.value !== base.content;
    const say = (message, error = false) => {
        status.textContent = message;
        status.className = 'small ' + (error ? 'text-danger' : 'text-body-secondary');
    };
    async function api(url, options = {}) {
        const response = await fetch(url, {
            ...options, cache: 'no-store', credentials: 'same-origin',
            headers: {Accept: 'application/json', 'X-CSRFToken': modal.dataset.csrf,
                ...(options.body ? {'Content-Type': 'application/json'} : {})}
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            const error = new Error(data.message || 'Sinkronisasi gagal. Periksa koneksi atau muat ulang sesi login.');
            error.data = data;
            error.status = response.status;
            throw error;
        }
        return data;
    }
    function apply(document) {
        // A slow poll must never roll back a newer successful save.
        if (base && document.version < base.version) return;
        const changed = base && document.version > base.version;
        // A plain text control keeps all note content inert (including HTML).
        if (editor.value !== document.content) {
            const start = editor.selectionStart, end = editor.selectionEnd;
            editor.value = document.content;
            editor.setSelectionRange(Math.min(start, editor.value.length), Math.min(end, editor.value.length));
        }
        base = document;
        pendingSince = null;
        clearTimeout(debounce);
        editor.disabled = false;
        editor.readOnly = !canEdit;
        say('Tersinkron · versi ' + document.version + (document.author_name ? ' · ' + document.author_name : ''));
        if (changed && !el('History').hidden) loadHistory();
    }
    function showConflict(document, message) {
        conflict = document;
        el('TeamVersion').value = document.content;
        el('Conflict').hidden = false;
        say(message || 'Gabungkan perubahan sebelum menyimpan. Tulisan Anda tetap tersimpan di kolom ini.', true);
    }
    async function sync(automatic = false) {
        if (saving || loading || conflict || blocked) return;
        if (dirty()) {
            // Keep polling from creating versions before the one-minute batch
            // is due, even while the member continues typing.
            if (!automatic || (pendingSince !== null && Date.now() - pendingSince >= autosaveDelay)) return save();
            return;
        }
        loading = true;
        try {
            const data = await api(modal.dataset.notesUrl);
            // Typing may have started while this request was in flight.
            if (!dirty() && !saving) apply(data.document);
        } catch (error) { say(error.message, true); }
        finally { loading = false; }
    }
    async function save() {
        if (!canEdit || !dirty() || saving || conflict || blocked) return;
        clearTimeout(debounce);
        saving = true;
        const submitted = editor.value, version = base.version;
        say('Menyimpan…');
        try {
            const data = await api(modal.dataset.notesUrl, {
                method: 'POST', body: JSON.stringify({content: submitted, base_version: version})
            });
            if (editor.value === submitted) apply(data.document);
            else if (data.document.content === submitted) {
                base = data.document;
                pendingSince = Date.now();
                scheduleSave();
                say('Perubahan terbaru menunggu disimpan…');
            } else {
                showConflict(data.document, 'Tim mengubah catatan saat Anda mengetik. Gabungkan tulisan terbaru Anda dengan versi tim.');
            }
            if (!el('History').hidden) loadHistory();
        } catch (error) {
            if (error.status === 409 && error.data.document) showConflict(error.data.document, error.message);
            else {
                blocked = !!error.status && error.status < 500;
                say(error.message + ' Tulisan Anda belum tersimpan; jangan tutup halaman.', true);
            }
        } finally { saving = false; }
    }
    function scheduleSave() {
        clearTimeout(debounce);
        if (pendingSince !== null) {
            debounce = setTimeout(save, Math.max(0, autosaveDelay - (Date.now() - pendingSince)));
        }
    }
    editor.addEventListener('input', () => {
        if (!dirty()) pendingSince = null;
        else if (pendingSince === null) pendingSince = Date.now();
        blocked = false;
        say(conflict ? 'Gabungkan perubahan, lalu klik Simpan hasil gabungan.' : 'Perubahan belum tersimpan…');
        scheduleSave();
    });
    el('Merge').addEventListener('click', () => {
        base = conflict;
        conflict = null;
        blocked = false;
        el('Conflict').hidden = true;
        if (dirty()) save(); else apply(base);
    });
    el('UseTeam').addEventListener('click', () => {
        apply(conflict);
        conflict = null;
        el('Conflict').hidden = true;
    });
    el('Retry').addEventListener('click', () => { blocked = false; sync(); });
    function node(tag, text, className) {
        const item = document.createElement(tag);
        item.textContent = text;
        if (className) item.className = className;
        return item;
    }
    async function loadHistory(append = false) {
        if (historyLoading) return;
        historyLoading = true;
        const list = el('HistoryList');
        try {
            const url = modal.dataset.historyUrl + (append && historyBefore ? '?before=' + historyBefore : '');
            const data = await api(url);
            if (!append) list.replaceChildren();
            if (!data.revisions.length && !append) list.append(node('p', 'Belum ada perubahan catatan.', 'small text-body-secondary'));
            for (const revision of data.revisions) {
                const entry = node('article', '', 'border rounded p-3 mb-2');
                const date = new Date(revision.created_at).toLocaleString('id-ID', {timeZone: 'Asia/Jakarta'});
                entry.append(node('div', revision.author_name + ' · ' + date + ' WIB · versi ' + revision.version, 'small fw-semibold mb-2'));
                for (const change of revision.changes) {
                    entry.append(node('div', 'Bagian mulai baris ' + change.line, 'small text-body-secondary'));
                    for (const [label, text, color] of [['Sebelum', change.before, 'text-danger'], ['Sesudah', change.after, 'text-success']]) {
                        entry.append(node('div', label, 'small fw-semibold ' + color));
                        const content = node('pre', text || '(kosong)', 'small mb-2 p-2 bg-body-tertiary border rounded');
                        content.style.whiteSpace = 'pre-wrap';
                        content.style.overflowWrap = 'anywhere';
                        entry.append(content);
                    }
                }
                list.append(entry);
            }
            historyBefore = data.next_before;
            el('HistoryMore').hidden = !historyBefore;
        } catch (error) { say('Riwayat: ' + error.message, true); }
        finally { historyLoading = false; }
    }
    el('HistoryToggle').addEventListener('click', () => {
        const section = el('History');
        section.hidden = !section.hidden;
        el('HistoryToggle').setAttribute('aria-expanded', String(!section.hidden));
        if (!section.hidden) loadHistory();
    });
    el('HistoryMore').addEventListener('click', () => loadHistory(true));
    modal.addEventListener('shown.bs.modal', () => {
        open = true;
        sync();
        timer = setInterval(() => { if (open && !document.hidden) sync(true); }, 2000);
    });
    modal.addEventListener('hide.bs.modal', event => {
        if (dirty() || saving || conflict) {
            event.preventDefault();
            if (!conflict) save();
            say('Tunggu sampai tersimpan atau selesaikan penggabungan sebelum menutup.', true);
        }
    });
    modal.addEventListener('hidden.bs.modal', () => { open = false; clearInterval(timer); clearTimeout(debounce); });
    window.addEventListener('beforeunload', event => {
        if (dirty() || saving || conflict) { event.preventDefault(); event.returnValue = ''; }
    });
})();
