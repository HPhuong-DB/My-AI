const { app, BrowserWindow, ipcMain, dialog, session } = require('electron');
const path = require('node:path');
const { createStaticServer } = require('./server.cjs');
const origin = 'http://127.0.0.1:5174';
let win, server;
app.setName('Huohuo');
if (!app.requestSingleInstanceLock()) { app.quit(); }
else {
  app.on('second-instance', () => { if (win) { win.restore(); win.focus(); } });
  app.whenReady().then(async () => {
    server = createStaticServer(path.join(__dirname, '..', 'dist'));
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(5174, '127.0.0.1', resolve); });
    win = new BrowserWindow({ width:440, height:700, minWidth:360, minHeight:480, title:'Huohuo', frame:false, alwaysOnTop:true, show:false, backgroundColor:'#101c1c',
      webPreferences:{ preload:path.join(__dirname,'preload.cjs'), contextIsolation:true, nodeIntegration:false, sandbox:true, webSecurity:true } });
    win.setAlwaysOnTop(true, 'floating');
    win.webContents.setWindowOpenHandler(() => ({ action:'deny' }));
    win.webContents.on('will-navigate', (event, url) => { if (new URL(url).origin !== origin) event.preventDefault(); });
    // Only explicitly requested microphone access from this app may reach an OS prompt.
    session.defaultSession.setPermissionRequestHandler((contents, permission, callback, details) => {
      callback(contents === win?.webContents && new URL(contents.getURL()).origin === origin && permission === 'media' && details.mediaTypes?.every(type => type === 'audio'));
    });
    for (const [channel, handler] of Object.entries({
      'window:minimize': () => win.minimize(),
      'window:close': () => win.close(),
      'window:pin': (value) => { if (typeof value !== 'boolean') return false; win.setAlwaysOnTop(value, 'floating'); return win.isAlwaysOnTop(); },
    })) ipcMain.handle(channel, (event, value) => {
      if (event.sender !== win?.webContents || event.senderFrame !== win.webContents.mainFrame || new URL(event.senderFrame.url).origin !== origin) throw new Error('Invalid window');
      return handler(value);
    });
    win.once('ready-to-show', () => win.show());
    win.on('closed', () => { win = null; app.quit(); });
    await win.loadURL(origin);
  }).catch(error => { dialog.showErrorBox('Không mở được Huohuo', `Hãy kiểm tra bản build và cổng 5174.\n${error.message}`); app.quit(); });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', () => server?.close());
}
