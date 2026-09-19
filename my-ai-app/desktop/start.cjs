// Editor terminals may set ELECTRON_RUN_AS_NODE; this launcher must start the app runtime.
const { spawn } = require('node:child_process');
const path = require('node:path');
const environment = { ...process.env };
delete environment.ELECTRON_RUN_AS_NODE;
const child = spawn(require('electron'), [path.join(__dirname, 'main.cjs')], { env: environment, stdio:'inherit' });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code || 0; });
