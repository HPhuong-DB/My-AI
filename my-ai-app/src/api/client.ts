export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
export const USER_ID = import.meta.env.VITE_USER_ID || 'default';

export async function requestJSON<T>(path: string, init: RequestInit = {}, timeoutMs = 35_000): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init.signal?.aborted) abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  const timer = window.setTimeout(abort, timeoutMs);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Máy chủ trả lỗi ${response.status}.`);
    return data as T;
  } finally {
    window.clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
}

export function userQuery() { return `user_id=${encodeURIComponent(USER_ID)}`; }

export async function setPrivacyConsent(permission: 'microphone' | 'screen', granted: boolean) {
  try {
    await requestJSON('/api/privacy/consent?' + userQuery(), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ permission, granted }),
    }, 10_000);
    return true;
  } catch { return false; }
}

export function formatDuration(ms: number) { return `${Math.round(ms)} ms`; }
