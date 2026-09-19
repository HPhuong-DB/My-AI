# Huohuo desktop

Run `npm run desktop` from the project, or double-click `Huohuo.command` on macOS. Keep the existing backend, MySQL and Ollama running; SearXNG is needed only for web lookup. Restart the backend after this change so HTTP/WebSocket requests from `http://127.0.0.1:5174` are accepted. If WS_ALLOWED_ORIGINS is overridden, add this origin to that setting as well.

The launcher builds the frontend and opens a 440×700 native window, initially always on top. Drag the header to move it. Minimize/close buttons are in the header; the always-on-top switch is in Tools. Closing the window ends the desktop process. No Vite server or browser tab is required; the app serves its built assets on loopback port 5174. A second instance focuses the existing window. This is a source-run desktop app, not a signed/packaged installer or transparent click-through desktop mascot.

Fresh installs: `npm install`, then `node node_modules/electron/install.js` if the Electron runtime has not downloaded. `desktop/start.cjs` removes ELECTRON_RUN_AS_NODE only for the child process so editor terminals start Electron correctly.

Both desktop and web use the configured VITE_API_URL/VITE_USER_ID at build time. Removing the history panel does not erase stored chat or memory. Tools contains capture/document tools, results, proactive preference, reminders, editable memories, pause and diagnostics. User mood/affection/interaction counters are no longer rendered.

Microphone currently uses the browser's SpeechRecognition API. Desktop Chromium may not supply a working speech recognition service; the app reports unsupported/service errors and text chat remains available. A dependable desktop microphone requires a dedicated STT integration. Screen capture in this initial desktop wrapper is not enabled; image/document file selection remains available. Live2D core is still loaded from the existing external Cubism URL, so an internet connection is required for that asset.

Security boundaries: renderer Node integration is off, context isolation and sandbox are on. The preload exposes only minimize, close and pin. IPC checks the sender and main-frame origin. The asset server binds only to 127.0.0.1 and rejects path escape, symlink escape and non-read methods. The app never launches arbitrary commands from chat.

Validation: 43 frontend tests, build/lint, desktop JavaScript syntax checks and 215 backend tests passed. Electron was launched successfully and observed listening on port 5174. Computer Use access was denied, so visual layout, dragging, pinning, microphone and end-to-end desktop chat have not been manually verified. In Tools, check connectivity after restarting the backend. Verify resizing, Escape/focus restoration for the tools dialog, and send a greeting before relying on the desktop session.
