import { useCallback, useEffect, useRef, useState } from 'react';
import { setPrivacyConsent } from '../api/client';
import type { ChatInputSource } from '../types';

interface RecognitionEvent { results: { length: number; [index: number]: { transcript?: string }[] }; error?: string; }
interface Recognition {
  continuous: boolean; interimResults: boolean; lang: string;
  start(): void; stop(): void; abort(): void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
}
declare global {
  interface Window { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition; }
}

export function useMicrophone(send: (text: string, source: ChatInputSource) => Promise<void>) {
  const [isListening, setListening] = useState(false);
  const [status, setStatus] = useState('Nhấn mic để nói chuyện');
  const recognitionRef = useRef<Recognition | null>(null);
  const attempt = useRef(0);
  const stop = useCallback(() => {
    attempt.current += 1;
    recognitionRef.current?.abort();
    setListening(false);
    void setPrivacyConsent('microphone', false);
  }, []);
  useEffect(() => {
    const Constructor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Constructor) return;
    const recognition = new Constructor();
    recognitionRef.current = recognition;
    recognition.lang = 'vi-VN'; recognition.continuous = false; recognition.interimResults = false;
    let received = false;
    recognition.onresult = (event) => {
      const text = Array.from(event.results).map((result) => result[0]?.transcript || '').join(' ').trim();
      if (!text) return;
      received = true; setListening(false); setStatus(`Đã nhận: ${text}`);
      void send(text, 'microphone').finally(() => {
        void setPrivacyConsent('microphone', false);
        setStatus('Sẵn sàng nghe');
      });
    };
    recognition.onerror = (event) => {
      if (event.error === 'aborted') return;
      setListening(false); void setPrivacyConsent('microphone', false);
      const errors: Record<string, string> = {
        'not-allowed': 'Mic bị từ chối quyền truy cập', 'service-not-allowed': 'Trình duyệt không cho phép nhận giọng nói',
        'no-speech': 'Chưa nghe thấy giọng nói, thử lại nhé', 'audio-capture': 'Không tìm thấy microphone', network: 'Dịch vụ nhận giọng nói đang lỗi mạng',
      };
      setStatus(errors[event.error || ''] || 'Không nhận được giọng nói, thử lại nhé');
    };
    recognition.onend = () => {
      setListening(false);
      if (!received) void setPrivacyConsent('microphone', false);
      received = false;
    };
    return () => {
      attempt.current += 1;
      recognition.onresult = null; recognition.onerror = null; recognition.onend = null;
      recognition.abort(); recognitionRef.current = null;
      void setPrivacyConsent('microphone', false);
    };
  }, [send]);
  const toggle = async () => {
    if (isListening) { stop(); setStatus('Đã dừng nghe'); return; }
    if (!recognitionRef.current) { setStatus('Trình duyệt chưa hỗ trợ mic'); return; }
    const current = ++attempt.current;
    setListening(true); setStatus('Đang chờ microphone…');
    const granted = await setPrivacyConsent('microphone', true);
    if (current !== attempt.current) { void setPrivacyConsent('microphone', false); return; }
    if (!granted) { setListening(false); setStatus('Chưa cấp được quyền dùng microphone'); return; }
    try { recognitionRef.current?.start(); setStatus('Đang nghe… nói đi nào'); }
    catch { stop(); setStatus('Mic đang bận, thử lại nhé'); }
  };
  return { isListening, status, toggle, stop };
}
