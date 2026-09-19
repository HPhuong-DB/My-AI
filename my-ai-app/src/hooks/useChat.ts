import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL, USER_ID, formatDuration, setPrivacyConsent } from '../api/client';
import { readChatStream } from '../api/chatStream';
import type { ChatInputSource, ChatStreamPayload } from '../types';
import type { Activity } from './useActivity';

interface Options {
  activity: Activity;
  show: (text: string, duration?: number) => void;
  hide: () => void;
  onReply: (reply: ChatStreamPayload) => void;
  onSettled?: () => void;
}

export function useChat({ activity: { begin, end }, show, hide, onReply, onSettled }: Options) {
  const [inputText, setInputText] = useState('');
  const draft = useRef('');
  const [error, setError] = useState('');
  const [retryText, setRetryText] = useState('');
  const [timing, setTiming] = useState('');
  const [historyRevision, setHistoryRevision] = useState(0);
  const refreshHistory = useCallback(() => setHistoryRevision((value) => value + 1), []);
  const controllerRef = useRef<AbortController | null>(null);
  const updateDraft = useCallback((text: string) => { draft.current = text; setInputText(text); }, []);
  const cancel = useCallback(() => controllerRef.current?.abort(), []);
  useEffect(() => cancel, [cancel]);

  const send = useCallback(async (override?: string, source: ChatInputSource = 'text') => {
    const text = (override ?? draft.current).trim();
    if (!text || !begin()) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    const timer = window.setTimeout(() => controller.abort(), 120_000);
    const started = performance.now();
    updateDraft(''); setError(''); setRetryText(text); hide();
    setTiming('Đang đo thời gian phản hồi…');
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, user_id: USER_ID, input_source: source }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(typeof data.detail === 'string' ? data.detail : `Máy chủ trả lỗi ${response.status}.`);
      }
      if (!response.body) throw new Error('Không nhận được luồng phản hồi.');
      const result = await readChatStream(response.body, show);
      if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
      setRetryText('');
      onReply(result);
      const metrics = result.timing || {};
      const searchStatus = result.search;
      const searchLabel = searchStatus ? (searchStatus.source_count > 0
        ? `Tra cứu: ${searchStatus.source_count} nguồn${searchStatus.unknown_dates ? ' (có nguồn thiếu ngày)' : ''} · `
        : `Tra cứu: ${searchStatus.status === 'unavailable' ? 'dịch vụ chưa phản hồi' : searchStatus.status === 'outdated' ? 'chỉ có nguồn cũ' : 'chưa có nguồn phù hợp'} · `) : '';
      setTiming(`${searchLabel}${metrics.generation_path === 'greeting' ? 'Chào nhanh · ' : ''}Định tuyến: ${metrics.routing_ms == null ? '-' : formatDuration(metrics.routing_ms)} · First token: ${metrics.first_token_ms == null ? '-' : formatDuration(metrics.first_token_ms)} · LLM: ${metrics.total_llm_ms == null ? '-' : formatDuration(metrics.total_llm_ms)} · ${metrics.tokens_per_second?.toFixed(1) || '-'} tok/s · Tổng: ${formatDuration(performance.now() - started)}`);
    } catch (cause) {
      const cancelled = controller.signal.aborted;
      controller.abort();
      const message = cancelled ? 'Phản hồi đã dừng hoặc quá thời gian chờ. Bạn có thể thử lại.'
        : cause instanceof TypeError ? 'Không kết nối được máy chủ. Hãy kiểm tra backend.'
        : cause instanceof Error ? cause.message : 'Không thể hoàn thành câu trả lời.';
      setError(message); show(message); updateDraft(text);
      setTiming(`Chat dừng sau ${formatDuration(performance.now() - started)}`);
    } finally {
      window.clearTimeout(timer);
      controllerRef.current = null;
      if (source === 'microphone') void setPrivacyConsent('microphone', false);
      setHistoryRevision((value) => value + 1);
      onSettled?.();
      end();
    }
  }, [begin, end, hide, onReply, onSettled, show, updateDraft]);
  return { inputText, updateDraft, send, cancel, error, retryText, timing, historyRevision, refreshHistory };
}
