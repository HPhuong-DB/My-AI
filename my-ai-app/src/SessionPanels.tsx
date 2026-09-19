import { useCallback, useEffect, useState } from 'react';

export function ServiceStatus({ apiUrl }: { apiUrl: string }) {
  const [status, setStatus] = useState('Đang kiểm tra kết nối…');
  const [checking, setChecking] = useState(false);
  const refresh = useCallback(async () => {
    setChecking(true);
    try {
      const response = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(10_000) });
      const data = await response.json();
      if (!data.checks) throw new Error('invalid_health');
      const database = data.checks.database ? 'Bộ nhớ: đã kết nối' : 'Bộ nhớ: mất kết nối MySQL';
      const model = data.checks.llm ? `AI: ${data.llm.model}` :
        data.llm?.error === 'model_not_found' ? `AI: chưa cài model ${data.llm.model}` : 'AI: chưa kết nối được model';
      setStatus(`${database} · ${model}`);
    } catch {
      setStatus('Không kết nối được máy chủ. Hãy khởi động backend rồi kiểm tra lại.');
    } finally {
      setChecking(false);
    }
  }, [apiUrl]);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 30_000);
    return () => { window.clearTimeout(timer); window.clearInterval(interval); };
  }, [refresh]);
  return <div className="service-status"><span role="status">{status}</span><button type="button" onClick={() => void refresh()} disabled={checking}>{checking ? 'Đang kiểm tra…' : 'Kiểm tra lại'}</button></div>;
}

export function ChatHistory({ apiUrl, userId, revision }: { apiUrl: string; userId: string; revision: number }) {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/chat/history?user_id=${encodeURIComponent(userId)}`, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error('history_failed');
      const data = await response.json();
      setMessages(data.messages);
      setError('');
    } catch {
      setError('Không thể tải lịch sử. Hãy kiểm tra kết nối bộ nhớ.');
    } finally { setLoading(false); }
  }, [apiUrl, userId]);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh, revision]);
  return <details className="history-panel"><summary>Lịch sử hội thoại</summary>
    <button type="button" onClick={() => void refresh()} disabled={loading}>{loading ? 'Đang tải…' : 'Tải lại'}</button>
    {error && <p role="alert">{error}</p>}
    {!error && !loading && messages.length === 0 && <p>Chưa có hội thoại đã lưu.</p>}
    <ol>{messages.map((message, index) => <li key={index}><strong>{message.role === 'user' ? 'Bạn' : 'Huohuo'}</strong><p>{message.content}</p></li>)}</ol>
  </details>;
}
