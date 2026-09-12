const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require('node:path').join(__dirname, 'whatsapp_bridge_cc.js'), 'utf8');
const boot = source.slice(source.indexOf('const httpServer = app.listen'));

test('duplicate port never overwrites QR status or opens the session', () => {
    let onListen, onError;
    const calls = [];
    vm.runInNewContext(boot, {
        app: { listen(port, callback) {
            onListen = callback;
            return { on(event, callback) { onError = callback; } };
        } },
        HTTP_PORT: 3100, BRIDGE_KEY: 'main', SESSION_PATH: 'session',
        CLIENT_ID: 'cc-main', INTERNAL_URL: 'http://localhost/inbound',
        console: { log() {}, error() {} },
        process: { exit(code) { calls.push(['exit', code]); } },
        setBridgeStatus(status) { calls.push(['status', status.state]); },
        armInitRecoveryWatchdog() { calls.push(['watchdog']); },
        client: { initialize() { calls.push(['initialize']); return Promise.resolve(); } },
        handleInitFailure() { assert.fail('unexpected init failure'); },
    });
    assert.deepEqual(calls, []);
    onError(new Error('EADDRINUSE'));
    assert.deepEqual(calls, [['exit', 1]]);
    calls.length = 0;
    onListen();
    assert.deepEqual(calls, [['status', 'starting'], ['watchdog'], ['initialize']]);
});
