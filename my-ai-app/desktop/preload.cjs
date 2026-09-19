const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('huohuoDesktop', {
  minimize: () => ipcRenderer.invoke('window:minimize'),
  close: () => ipcRenderer.invoke('window:close'),
  setPinned: (value) => ipcRenderer.invoke('window:pin', value),
});
