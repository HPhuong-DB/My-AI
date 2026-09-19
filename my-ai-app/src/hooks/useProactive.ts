import { useCallback, useEffect, useRef, useState } from 'react';
import { requestJSON, userQuery } from '../api/client';

interface Preferences { enabled: boolean; quiet_until: string | null; resume_on_message: boolean; }
export function useProactive() {
  const [settings, setSettings] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const version = useRef(0);
  const savingRef = useRef(false);
  const refresh = useCallback(async () => {
    if (savingRef.current) return;
    const current = ++version.current;
    try {
      const settings = await requestJSON<Preferences>(`/api/proactive/preferences?${userQuery()}`, {}, 10_000);
      if (current === version.current) { setSettings(settings); setError(''); }
    } catch { if (current === version.current) setError('Chưa đọc được tùy chọn chủ động.'); }
  }, []);
  const invalidate = useCallback(() => { version.current++; }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => { window.clearTimeout(timer); invalidate(); };
  }, [refresh, invalidate]);
  useEffect(() => {
    if (settings?.enabled || !settings?.quiet_until) return;
    const deadline = Date.parse(settings.quiet_until);
    if (!Number.isFinite(deadline)) return;
    const timer = window.setTimeout(() => void refresh(), Math.max(1000, deadline - Date.now() + 250));
    return () => window.clearTimeout(timer);
  }, [settings, refresh]);
  const toggle = async (enabled: boolean) => {
    savingRef.current = true;
    const current = ++version.current;
    setSaving(true); setError('');
    try {
      const settings = await requestJSON<Preferences>(`/api/proactive/preferences?${userQuery()}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
      }, 10_000);
      if (current === version.current) setSettings(settings);
    } catch { if (current === version.current) setError('Chưa lưu được tùy chọn chủ động.'); }
    finally { savingRef.current = false; if (current === version.current) setSaving(false); }
  };
  return { settings, saving, error, refresh, toggle };
}
