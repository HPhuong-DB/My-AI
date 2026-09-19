import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';
import { API_BASE_URL, userQuery } from '../api/client';
import { canPresentProactive } from '../api/proactiveGate';

interface Options { typing: boolean; reading: boolean; paused: boolean; listening: boolean; }
export function useAgentEvents(onPerception: (payload: Record<string, unknown>) => void, show: (text: string) => void,
  busy: RefObject<boolean>, options: Options, onReminder: () => void, onHistoryChanged: () => void) {
  const flags = useRef(options);
  const sendPresence = useRef<() => void>(() => {});
  const { typing, reading, paused, listening } = options;
  useEffect(() => {
    flags.current = { typing, reading, paused, listening };
    sendPresence.current();
  }, [typing, reading, paused, listening]);
  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    let attempts = 0;
    let typingUntil = 0;
    const seen = new Set<string>();
    const availability = () => ({
      visible: !document.hidden && document.hasFocus(),
      busy: busy.current || flags.current.paused || flags.current.listening,
      typing: flags.current.typing || Date.now() < typingUntil,
      reading: flags.current.reading,
      local_hour: new Date().getHours(),
    });
    const presence = () => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'presence', ...availability() }));
    };
    const onInput = () => { typingUntil = Date.now() + 15_000; presence(); };
    sendPresence.current = presence;
    const heartbeat = window.setInterval(presence, 15_000);
    document.addEventListener('visibilitychange', presence);
    document.addEventListener('input', onInput);
    window.addEventListener('focus', presence);
    window.addEventListener('blur', presence);
    const connect = () => {
      if (disposed) return;
      const url = new URL(API_BASE_URL);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.pathname = `${url.pathname.replace(/\/$/, '')}/api/ws`;
      url.search = userQuery();
      socket = new WebSocket(url);
      socket.onopen = () => { attempts = 0; presence(); };
      socket.onmessage = (message) => {
        if (disposed) return;
        try {
          const event = JSON.parse(message.data);
          if (event.type === 'proactive_ack' && event.accepted) onHistoryChanged();
          if (!event.payload) return;
          if (event.type === 'perception_completed') onPerception(event.payload);
          if (event.type === 'proactive_reminder') onReminder();
          if (!['proactive_reminder', 'proactive_suggestion'].includes(event.type)) return;
          if (typeof event.event_id !== 'string' || seen.has(event.event_id) || typeof event.payload.message !== 'string') return;
          if (!canPresentProactive(availability(), event.payload.expires_at)) return;
          seen.add(event.event_id);
          if (seen.size > 100) seen.delete(seen.values().next().value!);
          show(event.payload.message);
          // Suppress another event immediately, before the next React render.
          typingUntil = Date.now() + 30_000;
          socket?.send(JSON.stringify({ type: 'proactive_seen', event_id: event.event_id }));
          presence();
        } catch (cause) { console.warn('Không đọc được agent event:', cause); }
      };
      socket.onclose = () => { if (!disposed) timer = window.setTimeout(connect, Math.min(1000 * 2 ** attempts++, 10000)); };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      disposed = true; window.clearTimeout(timer); window.clearInterval(heartbeat); socket?.close();
      document.removeEventListener('visibilitychange', presence);
      document.removeEventListener('input', onInput);
      window.removeEventListener('focus', presence); window.removeEventListener('blur', presence);
      sendPresence.current = () => {};
    };
  }, [busy, onPerception, show, onReminder, onHistoryChanged]);
}
