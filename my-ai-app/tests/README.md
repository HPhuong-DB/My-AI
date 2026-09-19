# Frontend checks

Run `npm run build`, `npm run lint`, and `npm test` from `my-ai-app`.
The stream tests use Node's built-in test runner and TypeScript stripping (Node 22.18+ or 24+), with no added dependencies.

`chatStream.test.mjs` covers fragmented UTF-8/SSE, replacement after tools, premature EOF, backend errors, missing trailing newline, empty replies, and cancellation.

`reaction.test.mjs` checks content selection, negation/quoted examples, reading time, actual model asset references, expiry while loading, stale timers, cooldown and disposal. `live2dPlayer.test.mjs` uses a fake Cubism model to verify expression reset/cancellation, pose restoration, one-shot playback, asynchronous interruption and reduced motion. These tests validate orchestration, not the appearance of rendered pixels.

Manual browser checks after changes:

1. Load the page. The chat input and status render while Live2D loads separately.
2. Send a message, observe streamed text, and reload the history panel.
3. Edit/save/cancel/delete a memory for a disposable test user.
4. Stop a request while it is running; confirm input is retained and retry works after resume.
5. Test microphone consent, stopping before speech, denied consent, and speech submission.
6. Test OCR, image analysis, document upload, and screen sharing. Stop/cancel screen sharing and verify tracks end.
7. Restart the backend and verify WebSocket reconnects without duplicate notifications.
8. Navigate away while model loading is pending; verify no duplicate avatar or idle loops on return.
9. Try greetings, congratulations, sympathy, a technical answer and goodnight. Check that props disappear after expiry and neutral replies do not keep a previous face.
10. Send a second message during a gesture; stop the request, hide/restore the tab, and enable reduced motion. An expired reaction must not restart.
11. Compare a short reply and a long reply: the subtitle should remain longer for the long reply; the gesture should finish earlier rather than loop for the whole paragraph.

These browser checks are distinct from the automated stream checks. Browser automation permission was unavailable during the initial refactor verification.


Contextual proactive checks:

- `proactiveGate.test.mjs` covers presence, typing, reading, busy state, daytime boundaries and offer expiry. Backend tests cover topic evidence, deleted memory, quiet requests, persistent cooldowns, acknowledgement and WebSocket cleanup.
- Manual UI: enable the proactive checkbox, discuss a stored interest, then leave the focused window idle for at least five minutes. Expect at most one invitation until replying. Repeat with a draft, visible reply bubble, hidden tab, microphone active, and disabled checkbox: expect silence.
- Say “Đừng làm phiền 1 phút”, confirm the checkbox becomes unchecked, then verify it becomes checked after expiry. Direct chat must remain usable. Say “Mình đi ngủ”, then send another message to resume.
- A shown invitation should appear once in history after reload. An expired/dropped invitation must not appear. Existing reminders remain visible in their panel during quiet mode.
- These are manual acceptance steps; automated gate/transport tests do not establish visual browser behaviour.

Desktop asset server: desktopServer.test.mjs verifies public asset delivery and rejection of path/symlink escape and write methods. Manual UI checks: resize to mobile/desktop, open Tools, press Escape, confirm focus returns to the opener, inspect no history/interaction panels, send a greeting, and check desktop pin/minimize/close. Native microphone depends on the available STT service; do not interpret a microphone icon as proof speech recognition is supported.
