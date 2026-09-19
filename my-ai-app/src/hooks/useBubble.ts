import { useCallback, useEffect, useRef, useState } from 'react';

export function useBubble() {
  const [text, setText] = useState('');
  const [visible, setVisible] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const clear = useCallback(() => window.clearTimeout(timer.current), []);
  const hide = useCallback(() => { clear(); setVisible(false); }, [clear]);
  const show = useCallback((value: string, duration?: number) => {
    clear(); setText(value); setVisible(true);
    if (duration) timer.current = window.setTimeout(() => setVisible(false), duration);
  }, [clear]);
  useEffect(() => clear, [clear]);
  return { text, visible, show, hide };
}
