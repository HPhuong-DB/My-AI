# Frontend organization

`App.tsx` composes the page and connects features. Feature state and side effects live in hooks; JSX panels receive their view models. API protocol code is separate from React and can be tested without a browser.

- `api/client.ts`: backend URL/user configuration, JSON requests with timeout covering the body, privacy consent.
- `api/chatStream.ts`: SSE/UTF-8 decoding, replacement events, completion validation, reader cancellation.
- `types.ts`: shared API and avatar handle types; no runtime PIXI dependency.
- `hooks/useActivity.ts`: shared foreground-operation gate and emergency-stop block.
- `hooks/useChat.ts`: draft, streaming chat, retry, cancellation, timing, history refresh.
- `hooks/useBubble.ts`: subtitle text and expiry timer.
- `hooks/useMemories.ts` + `components/MemoryPanel.tsx`: load/edit/delete personal memory.
- `hooks/useReminders.ts` + `components/ReminderPanel.tsx`: due reminders and completion. No speech output.
- `hooks/useMicrophone.ts`: browser speech recognition, consent and listener cleanup.
- `hooks/usePerception.ts` + `components/PerceptionPanel.tsx`: OCR, image analysis, screen capture, document reading, cancellation and capture-track cleanup.
- `hooks/useAgentEvents.ts`: WebSocket reconnect, privacy-preserving presence heartbeat, proactive expiry/availability gate, and display acknowledgement/history refresh.
- `hooks/useProactive.ts`: persisted proactive toggle, natural-language boundary refresh after chat, UTC timed-quiet expiry refresh.
- `api/proactiveGate.ts`: pure rules preventing stale offers or interruptions while typing, reading, busy, hidden, or outside daytime hours.
- `components/AvatarStage.tsx`: lazy-loaded PIXI/Live2D, neutral breathing, pending-load cleanup. Exposes `AvatarHandle.play(plan)` and `reset()`.
- `avatar/reaction.ts`: final-text reaction selection and subtitle reading time; ignores arbitrary model motion/expression names.
- `avatar/reactionController.ts`: one active reaction, absolute expiry while loading, interruption and gesture cooldown.
- `avatar/live2dPlayer.ts`: Cubism adapter, non-looping motions, expression cancellation/reset and 350 ms return to initial pose.
- `components/ChatComposer.tsx`: text input, send/retry, microphone and stop buttons.
- `SessionPanels.tsx`: service status and persisted conversation history.
- `App.css`: existing visual styles, retained to avoid a simultaneous redesign.

Keep feature-specific changes in their hook/panel; avoid adding fetch calls or PIXI details to App. Use the shared activity gate for new foreground actions and release it in `finally`. Keep emergency stop available during requests. All new asynchronous resources need cleanup on cancel/unmount.

Validation: `npm run build`, `npm run lint`, `npm test`. See `../tests/README.md` for remaining browser checks.

Refactor measurement: App went from 1,101 lines to 100. The minified entry bundle went from about 829 KB to 223 KB; the 613 KB Live2D chunk is loaded separately. Total JavaScript has not meaningfully shrunk, and no browser-load speed claim is made from bundle size alone. Vite still warns about the size of the avatar chunk.

The main screen is now stage + compact composer. ToolsDialog uses a native modal dialog; tool controls/results, preferences, reminders, memories and diagnostics live there. ChatHistory is no longer mounted; storage is unchanged. Icon contains local SVG icons. AvatarStage resizes its renderer/model to the actual viewport. Optional window.huohuoDesktop is a narrow preload bridge for window controls, never backend/file access.

AvatarStage follows mouse/pen movement inside the character stage through Cubism FocusController, capped at 0.30 horizontally and 0.22 vertically. Gaze returns to center on pointer leave/cancel or window blur and resets when hidden/reduced-motion is enabled. Pointer listeners are removed on unmount. This tracks the app window only, not the global desktop cursor.
