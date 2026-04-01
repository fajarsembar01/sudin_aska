(function () {
  function scoreBadgeClass(pct) {
    if (pct < 55) return 'score-badge-red';
    if (pct < 70) return 'score-badge-orange';
    if (pct < 85) return 'score-badge-yellow';
    return 'score-badge-green';
  }

  function updateBadgeClasses(el, pct) {
    if (!el) return;
    el.classList.remove('score-badge-red', 'score-badge-orange', 'score-badge-yellow', 'score-badge-green');
    el.classList.add(scoreBadgeClass(pct));
  }

  function initAssessmentUI(config) {
    const state = {
      assessmentId: config.assessmentId,
      schoolId: config.schoolId,
      scaleMax: config.scaleMax || 5,
      scoreEndpoint: config.scoreEndpoint,
      noteEndpoint: config.noteEndpoint,
      floatingScoreValueId: config.floatingScoreValueId || 'floatingScoreValue',
      floatingScoreCountId: config.floatingScoreCountId || 'floatingScoreCount',
      scoreProgressBarId: config.scoreProgressBarId || 'scoreProgressBar',
      scoreSelector: config.scoreSelector || '.score-btn.selected',
      groupSelector: config.groupSelector || '.score-group',
      itemSelector: config.itemSelector || '.aspect-item',
      roomSelector: config.roomSelector || '.room-item',
      scoreBadgeSelector: config.scoreBadgeSelector || '.room-score-badge',
      roomBadgePrefix: config.roomBadgePrefix || 'roomBadge',
      roomScorePrefix: config.roomScorePrefix || 'roomScore',
      scoreBtnSelector: config.scoreBtnSelector || '.score-btn',
      pendingRequests: {},
    };

    function saveScoreRequest(ownerId, aspectId, score, extra) {
      const key = `${ownerId}:${aspectId}`;
      const prev = state.pendingRequests[key] || Promise.resolve();
      const payload = Object.assign({
        assessment_id: state.assessmentId,
        score,
        aspect_id: aspectId,
      }, extra || {});
      const promise = prev.catch(() => null).then(() => fetch(state.scoreEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(res => res.json()).then(data => {
        if (!data.success) throw new Error(data.message || 'Gagal menyimpan skor');
        return data;
      }));
      state.pendingRequests[key] = promise;
      return promise.finally(() => {
        if (state.pendingRequests[key] === promise) delete state.pendingRequests[key];
      });
    }

    function updateScoreSummary() {
      const selected = document.querySelectorAll(state.scoreSelector);
      let total = 0;
      selected.forEach(btn => total += parseInt(btn.dataset.score, 10) || 0);
      const count = selected.length;
      const totalItems = document.querySelectorAll(state.itemSelector).length;
      const pct = count ? ((total / count) / state.scaleMax) * 100 : 0;
      const valueEl = document.getElementById(state.floatingScoreValueId);
      const countEl = document.getElementById(state.floatingScoreCountId);
      const bar = document.getElementById(state.scoreProgressBarId);
      if (valueEl) valueEl.textContent = pct.toFixed(1).replace('.', ',');
      if (countEl) countEl.textContent = `${count}/${totalItems}`;
      if (bar) bar.style.width = `${totalItems ? (count / totalItems) * 100 : 0}%`;
    }

    function updateGroupScore(groupEl) {
      if (!groupEl) return;
      const ownerId = groupEl.dataset.schoolRoomId;
      const room = document.getElementById(`room${ownerId}`);
      const scoreDisplay = document.getElementById(`${state.roomScorePrefix}${ownerId}`);
      const roomBadge = document.getElementById(`${state.roomBadgePrefix}${ownerId}`);
      if (!room || !scoreDisplay) return;
      const selected = room.querySelectorAll(state.scoreSelector);
      let totalScore = 0;
      selected.forEach(btn => totalScore += parseInt(btn.dataset.score, 10) || 0);
      const totalAspects = room.querySelectorAll(state.groupSelector).length;
      const selectedCount = room.querySelectorAll(state.scoreSelector).length;
      if (roomBadge) roomBadge.textContent = `${selectedCount}/${totalAspects}`;
      if (selectedCount === 0) {
        scoreDisplay.textContent = '0.0';
        updateBadgeClasses(scoreDisplay, 0);
        return;
      }
      const pct = ((totalScore / selectedCount) / state.scaleMax) * 100;
      scoreDisplay.textContent = pct.toFixed(1);
      updateBadgeClasses(scoreDisplay, pct);
    }

    function selectScore(btn) {
      const group = btn.closest(state.groupSelector);
      if (!group) return;
      const ownerId = parseInt(group.dataset.schoolRoomId, 10);
      const aspectId = parseInt(group.dataset.aspectId, 10);
      const score = parseInt(btn.dataset.score, 10);
      group.querySelectorAll(state.scoreBtnSelector).forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      updateScoreSummary();
      updateGroupScore(group);
      const extra = {};
      if (config.scorePayloadFactory) Object.assign(extra, config.scorePayloadFactory(ownerId, aspectId, score) || {});
      saveScoreRequest(ownerId, aspectId, score, extra).catch(err => {
        if (config.onError) config.onError(err);
      });
    }

    function saveNote(textarea, ownerId) {
      if (!state.noteEndpoint) return;
      fetch(state.noteEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assessment_id: state.assessmentId,
          school_room_id: ownerId,
          component_id: ownerId,
          note: textarea.value,
          notes: textarea.value
        })
      }).catch(() => null);
    }

    function updateAllGroups() {
      document.querySelectorAll(state.groupSelector).forEach(group => updateGroupScore(group));
      updateScoreSummary();
    }

    window.selectScore = selectScore;
    window.updateAssessmentScoreSummary = updateScoreSummary;
    window.updateAssessmentGroupScore = updateGroupScore;
    window.saveAssessmentNote = saveNote;
    window.saveNoteWithDebounce = saveNote;
    window.updateAssessmentAllGroups = updateAllGroups;
    window.scoreBadgeClass = scoreBadgeClass;

    const searchInput = document.getElementById(config.searchInputId || 'roomSearchAssessment');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        const query = this.value.toLowerCase().trim();
        document.querySelectorAll(state.roomSelector).forEach(room => {
          const roomName = room.dataset.roomName || '';
          room.style.display = query.length < 2 || roomName.includes(query) ? '' : 'none';
        });
      });
    }

    const hideBtn = document.getElementById(config.hideScoreCardBtnId || 'hideScoreCardBtn');
    const showBtn = document.getElementById(config.showScoreCardBtnId || 'showScoreCardBtn');
    const card = document.getElementById(config.floatingScoreCardId || 'floatingScoreCard');
    if (hideBtn && card) {
      hideBtn.addEventListener('click', () => {
        card.classList.add('d-none');
        if (showBtn) showBtn.classList.remove('d-none');
      });
    }
    if (showBtn && card) {
      showBtn.addEventListener('click', () => {
        card.classList.remove('d-none');
        showBtn.classList.add('d-none');
      });
    }

    updateAllGroups();
    return { updateAllGroups, updateScoreSummary, selectScore, saveNote };
  }

  window.initAssessmentUI = initAssessmentUI;
  window.scoreBadgeClass = scoreBadgeClass;
})();
