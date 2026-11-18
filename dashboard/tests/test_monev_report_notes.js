// Run with: node --test dashboard/tests/test_monev_report_notes.js
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('dashboard/static/js/monev-report-notes.js', 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup() {
    const elements = new Map(), requests = [], timers = new Map();
    let timerId = 0, interval, now = 100000;
    class TestDate extends Date {
        static now() { return now; }
    }
    function element(id) {
        if (!elements.has(id)) elements.set(id, {
            value: '', hidden: typeof id === 'string' && ['Conflict', 'History', 'HistoryMore'].some(suffix => id.endsWith(suffix)),
            selectionStart: 0, selectionEnd: 0, style: {}, handlers: {},
            addEventListener(name, fn) { this.handlers[name] = fn; },
            setSelectionRange() {}, setAttribute() {}, append() {}, replaceChildren() {}
        });
        return elements.get(id);
    }
    element('reportNotesModal').dataset = {canEdit: 'true', notesUrl: '/notes', historyUrl: '/history', csrf: 'test'};
    const document = {hidden: false, getElementById: element, createElement: () => element(Symbol())};
    vm.runInNewContext(source, {
        document, window: {addEventListener() {}}, Date: TestDate,
        fetch(url, options) {
            return new Promise(resolve => requests.push({url, options, respond(status, body) {
                resolve({ok: status < 400, status, json: async () => body});
            }}));
        },
        setTimeout(fn, delay) { const id = ++timerId; timers.set(id, {fn, due: now + delay}); return id; },
        clearTimeout(id) { timers.delete(id); },
        setInterval(fn) { interval = fn; return 1; }, clearInterval() {}
    });
    const get = suffix => element('reportNotes' + suffix);
    const event = (suffix, name) => get(suffix).handlers[name]({preventDefault() {}});
    return {
        get, requests, event, poll: () => interval(),
        advance(ms) { now += ms; },
        async load(content = 'Awal', version = 1) {
            event('Modal', 'shown.bs.modal');
            requests.shift().respond(200, {success: true, document: {content, version}});
            await flush();
        },
        input(content) { get('Editor').value = content; event('Editor', 'input'); },
        async autosave() {
            const [id, timer] = [...timers].pop();
            timers.delete(id);
            now = Math.max(now, timer.due);
            timer.fn();
            await flush();
        }
    };
}

test('autosave preserves typing that occurs while saving', async () => {
    const app = setup();
    await app.load();
    app.input('Awal satu');
    await app.autosave();
    const request = app.requests.shift();
    assert.equal(JSON.parse(request.options.body).base_version, 1);
    app.input('Awal satu dua');
    request.respond(200, {success: true, document: {content: 'Awal satu', version: 2}});
    await flush();
    assert.equal(app.get('Editor').value, 'Awal satu dua');
    await app.autosave();
    const next = app.requests.shift();
    assert.deepEqual(JSON.parse(next.options.body), {content: 'Awal satu dua', base_version: 2});
    next.respond(200, {success: true, document: {content: 'Awal satu dua', version: 3}});
    await flush();
    assert.match(app.get('Status').textContent, /versi 3/);
});

test('polling batches changes for one minute even when typing continues', async () => {
    const app = setup();
    await app.load();
    app.input('Catatan');
    app.advance(30000);
    app.poll();
    assert.equal(app.requests.length, 0);
    app.input('Catatan lanjutan');
    app.advance(29000);
    app.poll();
    assert.equal(app.requests.length, 0);
    app.advance(1000);
    app.poll();
    assert.equal(app.requests.length, 1);
    assert.deepEqual(JSON.parse(app.requests.shift().options.body), {content: 'Catatan lanjutan', base_version: 1});
});

test('manual synchronization still saves immediately before the minute is up', async () => {
    const app = setup();
    await app.load();
    app.input('Simpan sekarang');
    app.event('Retry', 'click');
    assert.equal(app.requests.length, 1);
    assert.equal(JSON.parse(app.requests.shift().options.body).content, 'Simpan sekarang');
});

test('a slow poll cannot replace a newer saved version', async () => {
    const app = setup();
    await app.load();
    app.poll();
    const poll = app.requests.shift();
    app.input('Baru');
    await app.autosave();
    app.requests.shift().respond(200, {success: true, document: {content: 'Baru', version: 2}});
    await flush();
    poll.respond(200, {success: true, document: {content: 'Awal', version: 1}});
    await flush();
    assert.equal(app.get('Editor').value, 'Baru');
    assert.match(app.get('Status').textContent, /versi 2/);
});

test('conflicts retain local text and require an explicit merge', async () => {
    const app = setup();
    await app.load();
    app.input('Tulisan saya');
    await app.autosave();
    app.requests.shift().respond(409, {success: false, message: 'Bentrok', document: {content: 'Tulisan tim', version: 2}});
    await flush();
    assert.equal(app.get('Editor').value, 'Tulisan saya');
    assert.equal(app.get('TeamVersion').value, 'Tulisan tim');
    assert.equal(app.get('Conflict').hidden, false);
    app.poll();
    assert.equal(app.requests.length, 0);
    app.input('Tulisan saya dan tim');
    app.event('Merge', 'click');
    assert.deepEqual(JSON.parse(app.requests.shift().options.body), {content: 'Tulisan saya dan tim', base_version: 2});
});

test('remote edits sync when idle and cannot replace unsaved local input', async () => {
    const app = setup();
    await app.load();
    app.poll();
    app.requests.shift().respond(200, {success: true, document: {content: 'Dari anggota tim', version: 2}});
    await flush();
    assert.equal(app.get('Editor').value, 'Dari anggota tim');
    app.poll();
    const request = app.requests.shift();
    app.input('Tulisan lokal');
    request.respond(200, {success: true, document: {content: 'Versi tim terbaru', version: 3}});
    await flush();
    assert.equal(app.get('Editor').value, 'Tulisan lokal');
});
