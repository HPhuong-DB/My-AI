import { useCallback, useEffect, useState } from 'react';
import { requestJSON, userQuery } from '../api/client';
import type { ReminderNotification } from '../types';

export function useReminders(show: (text: string, duration?: number) => void) {
  const [reminders, setReminders] = useState<ReminderNotification[]>([]);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try {
      const data = await requestJSON<{ notifications: ReminderNotification[] }>('/api/tools/reminders/notifications?' + userQuery(), {}, 10_000);
      setReminders(data.notifications || []); setError('');
    } catch { setError('Không thể tải nhắc nhở.'); }
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timer); }, [refresh]);
  const complete = async (id: number) => {
    try {
      const data = await requestJSON<{ message?: string }>(`/api/tools/reminders/${id}/complete?${userQuery()}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completion_message: 'Mình đã hoàn thành xong rồi, cảm thấy nhẹ hơn nhiều.', emotion: 'relieved' }),
      }, 10_000);
      show(data.message || 'Đã đánh dấu hoàn thành.', 7000);
      await refresh();
    } catch { setError('Không thể đánh dấu nhắc nhở hoàn thành.'); }
  };
  return { reminders, setReminders, refresh, complete, error };
}
