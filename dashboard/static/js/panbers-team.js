/* Shared Panberss fields and room presence, with explicit conflict resolution. */
(function () {
  window.createPanbersTeamClient = function (config) {
    const versions = new Map();
    const pending = new Map();
    const conflicts = new Map();
    const failed = new Map();
    const clientId = crypto.randomUUID();
    const status = document.getElementById('teamSyncStatus');
    const conflictArea = document.getElementById('teamSyncConflicts');
    let latest = config.initial;
    let polling = false;
    let stopped = false;
    function key(room, field) { return `${room}/${field}`; }
    function fieldOf(payload) { return payload.aspect_id ? `score:${payload.aspect_id}` : 'note'; }
    function setStatus(text, error) {
      status.textContent = text;
      status.classList.toggle('text-danger', !!error);
      const notice = document.getElementById('teamSyncNotice');
      if (notice) notice.hidden = !error && !stopped;
    }
    function valueIn(snapshot, payload) {
      if (payload.aspect_id) {
        const row = snapshot.scores.find(r => r.school_room_id === payload.school_room_id && r.aspect_id === payload.aspect_id);
        return row ? row.score : null;
      }
      const row = snapshot.notes.find(r => r.school_room_id === payload.school_room_id);
      return row ? row.notes : '';
    }
    function paint(payload, value) {
      if (payload.aspect_id) {
        const group = document.querySelector(`.score-group[data-school-room-id="${payload.school_room_id}"][data-aspect-id="${payload.aspect_id}"]`);
        if (group) group.querySelectorAll('.score-btn').forEach(button => button.classList.toggle('selected', value !== null && Number(button.dataset.score) === Number(value)));
      } else {
        const textarea = document.querySelector(`#room${payload.school_room_id} textarea`);
        if (textarea && textarea.value !== value) textarea.value = value || '';
      }
    }
    function lockEditor() {
      document.querySelectorAll('#roomAccordion button, #roomAccordion textarea, #roomAccordion input, #submitAssessmentForm button, #saveDraftForm button').forEach(el => { el.disabled = true; });
    }
    function apply(snapshot) {
      latest = snapshot;
      const incoming = new Map(snapshot.versions.map(v => [key(v.school_room_id, v.field_key), v]));
      snapshot.versions.filter(v => v.field_key === 'photo').forEach(v => {
        const field = key(v.school_room_id, 'photo');
        versions.set(field, Math.max(versions.get(field) || 0, v.version));
      });
      snapshot.scores.forEach(row => {
        const field = key(row.school_room_id, `score:${row.aspect_id}`);
        const version = incoming.get(field)?.version || 0;
        if (!pending.has(field) && !conflicts.has(field) && !failed.has(field) && version >= (versions.get(field) || 0)) {
          paint(row, row.score); versions.set(field, version);
        }
      });
      snapshot.notes.forEach(row => {
        const field = key(row.school_room_id, 'note');
        const version = incoming.get(field)?.version || 0;
        if (!pending.has(field) && !conflicts.has(field) && !failed.has(field) && version >= (versions.get(field) || 0)) {
          paint(row, row.notes); versions.set(field, version);
        }
      });
      document.querySelectorAll('.team-room-presence').forEach(label => {
        const names = [...new Set(snapshot.presence.filter(p => p.school_room_id === Number(label.dataset.roomId) && p.user_id !== config.userId).map(p => p.name))];
        label.textContent = names.length ? `${names.join(', ')} sedang menilai` : '';
        label.setAttribute('aria-label', names.length ? `${names.join(', ')} sedang menilai` : '');
        label.setAttribute('title', names.length ? `${names.join(', ')} sedang menilai` : '');
      });
      (snapshot.room_status || []).forEach(room => {
        const label = document.querySelector(`.team-room-status[data-room-id="${room.school_room_id}"]`);
        if (!label) return;
        if (!room.last_editor) label.textContent = 'Belum pernah dinilai';
        else if (Number(room.remaining) === 0) label.textContent = `Sudah dinilai oleh : ${room.last_editor}`;
        else label.textContent = `Terakhir dinilai oleh : ${room.last_editor} (${room.remaining} aspek belum dinilai)`;
      });
      if (config.onPhotos) config.onPhotos(snapshot.photos);
      if (window.updateAssessmentAllGroups) window.updateAssessmentAllGroups();
      if (snapshot.status !== 'draft') {
        stopped = true;
        setStatus('Penilaian sudah dikirim anggota tim. Isian dikunci; buka hasil melalui tautan di bawah.');
        lockEditor();
        const link = document.getElementById('teamResultLink');
        link.href = snapshot.view_url || config.viewUrl; link.hidden = false;
      }
    }
    async function sync() {
      if (polling || stopped) return;
      polling = true;
      const open = document.querySelector('#roomAccordion .collapse.show');
      try {
        const response = await fetch(config.stateUrl, {
          method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': config.csrf},
          body: JSON.stringify({client_id: clientId, school_room_id: open ? Number(open.id.replace('room', '')) : null})
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
          if (response.status === 403) { stopped = true; lockEditor(); }
          throw new Error(data.message || 'Gagal sinkronisasi tim.');
        }
        apply(data);
        if (!stopped && !pending.size && !conflicts.size && !failed.size) setStatus('');
      } catch (error) { setStatus(error.message || 'Koneksi terputus. Isian yang belum tersimpan tetap di halaman ini.', true); }
      finally { polling = false; }
    }
    function showIssue(field, endpoint, payload, message, conflict) {
      const store = conflict ? conflicts : failed;
      store.set(field, payload);
      document.getElementById(`team-issue-${field.replace(/[^\w]/g, '-')}`)?.remove();
      const panel = document.createElement('div');
      panel.id = `team-issue-${field.replace(/[^\w]/g, '-')}`;
      panel.className = 'alert alert-warning small';
      const text = document.createElement('p');
      const roomName = document.querySelector(`.room-item[data-school-room-id="${payload.school_room_id}"] .room-header h5`)?.textContent;
      const aspectName = payload.aspect_id ? document.querySelector(`#aspect-room-${payload.school_room_id}-${payload.aspect_id} .aspect-name`)?.textContent : 'Catatan';
      const label = [roomName, aspectName].filter(Boolean).join(' · ');
      text.textContent = (label ? label + ': ' : '') + message;
      const local = document.createElement('p');
      local.textContent = `Isian Anda: ${payload.aspect_id ? payload.score : payload.notes}`;
      const remote = document.createElement('p');
      remote.textContent = `Versi tim: ${valueIn(latest, payload) ?? 'Belum diisi'}`;
      const useTeam = document.createElement('button');
      useTeam.type = 'button'; useTeam.className = 'btn btn-sm btn-outline-secondary me-2'; useTeam.textContent = 'Gunakan versi tim';
      function clear() { conflicts.delete(field); failed.delete(field); panel.remove(); }
      function adoptVersion() {
        const row = latest.versions.find(v => key(v.school_room_id, v.field_key) === field);
        versions.set(field, row?.version || 0);
      }
      useTeam.onclick = function () { adoptVersion(); paint(payload, valueIn(latest, payload)); clear(); window.updateAssessmentAllGroups?.(); };
      const retry = document.createElement('button');
      retry.type = 'button'; retry.className = 'btn btn-sm btn-warning'; retry.textContent = 'Simpan isian saya';
      retry.onclick = function () {
        if (conflict) adoptVersion();
        clear(); request(endpoint, payload).catch(() => {});
      };
      panel.append(text, local, remote, useTeam, retry); conflictArea.append(panel);
    }
    function request(endpoint, payload) {
      const field = key(payload.school_room_id, fieldOf(payload));
      if (stopped) return Promise.reject(new Error('Penilaian sudah dikirim atau akses berubah.'));
      if (conflicts.has(field) || failed.has(field)) {
        showIssue(field, endpoint, payload, 'Periksa perbedaan isian sebelum menyimpan kembali.', conflicts.has(field));
        return Promise.reject(new Error('Masih ada isian yang perlu diperiksa.'));
      }
      const previous = pending.get(field) || Promise.resolve();
      const task = previous.catch(() => {}).then(async function () {
        if (conflicts.has(field) || failed.has(field)) {
          showIssue(field, endpoint, payload, 'Periksa perbedaan isian sebelum menyimpan kembali.', conflicts.has(field));
          throw new Error('Selesaikan perbedaan isian terlebih dahulu.');
        }
        setStatus('');
        const baseVersion = versions.get(field) || 0;
        try {
          const response = await fetch(endpoint, {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': config.csrf},
            body: JSON.stringify({...payload, base_version: baseVersion})
          });
          const result = await response.json();
          if (!response.ok || !result.success) {
            const error = new Error(result.message || 'Perubahan belum tersimpan.'); error.conflict = response.status === 409; throw error;
          }
          versions.set(field, result.version);
          return result;
        } catch (error) {
          await sync();
          showIssue(field, endpoint, payload, error.message, !!error.conflict);
          setStatus('Ada perubahan yang belum tersimpan. Periksa pesan di bawah.', true);
          throw error;
        }
      });
      pending.set(field, task);
      task.finally(() => { if (pending.get(field) === task) pending.delete(field); }).catch(() => {});
      return task;
    }
    function hasUnsaved() { return pending.size || conflicts.size || failed.size; }
    document.querySelectorAll('#submitAssessmentForm, #saveDraftForm').forEach(form => {
      form.addEventListener('submit', event => {
        if (hasUnsaved()) { event.preventDefault(); event.stopImmediatePropagation(); setStatus('Tunggu penyimpanan dan selesaikan perbedaan isian sebelum melanjutkan.', true); status.scrollIntoView({block:'center'}); }
      }, true);
    });
    window.addEventListener('beforeunload', event => { if (hasUnsaved()) { event.preventDefault(); event.returnValue = ''; } });
    config.initial.versions.forEach(v => versions.set(key(v.school_room_id, v.field_key), v.version));
    apply(config.initial);
    document.addEventListener('shown.bs.collapse', sync);
    document.addEventListener('hidden.bs.collapse', sync);
    const timer = window.setInterval(() => { if (!stopped) sync(); else window.clearInterval(timer); }, 2000);
    sync();
    return {request, sync, hasUnsaved, photoVersion: roomId => versions.get(key(roomId, 'photo')) || 0};
  };
})();
