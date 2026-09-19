import { useCallback, useRef, useState } from 'react';

/** One foreground operation at a time, including mic and file-triggered chat. */
export function useActivity() {
  const [isBusy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const blockedRef = useRef(false);
  const begin = useCallback(() => {
    if (busyRef.current || blockedRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    return true;
  }, []);
  const end = useCallback(() => { busyRef.current = false; setBusy(false); }, []);
  const block = useCallback((value: boolean) => { blockedRef.current = value; }, []);
  return { isBusy, busyRef, begin, end, block };
}
export type Activity = ReturnType<typeof useActivity>;
