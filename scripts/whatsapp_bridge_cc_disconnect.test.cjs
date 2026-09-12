const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require('node:path').join(__dirname, 'whatsapp_bridge_cc.js'), 'utf8');
const start = source.indexOf('client.on("disconnected"');
const end = source.indexOf('// ── Watchdog:', start);
const handlerSource = source.slice(start, end);

function loadHandler() {
    let handler;
    const calls = [];
    vm.runInNewContext(handlerSource, {
        client: { on(event, callback) { assert.equal(event, 'disconnected'); handler = callback; } },
        clearInitRecoveryWatchdog() { calls.push(['clear']); },
        setBridgeStatus(status) { calls.push(['status', status.state, status.message]); },
        armInitRecoveryWatchdog() { calls.push(['watchdog']); },
        console: { warn() {} },
        setTimeout(callback) { calls.push(['timer']); callback(); },
        process: { exit(code) { calls.push(['exit', code]); } },
    });
    return { handler, calls };
}

test('LOGOUT lets whatsapp-web.js finish its own QR reset', () => {
    const { handler, calls } = loadHandler();
    handler('LOGOUT');
    assert.deepEqual(calls, [
        ['clear'],
        ['status', 'starting', 'Sesi WhatsApp keluar. Menunggu QR baru...'],
        ['watchdog'],
    ]);
});

test('other disconnect exits so systemd can create a fresh client', () => {
    const { handler, calls } = loadHandler();
    handler('UNPAIRED');
    assert.deepEqual(calls, [
        ['clear'],
        ['status', 'disconnected', 'UNPAIRED'],
        ['timer'],
        ['exit', 1],
    ]);
});
