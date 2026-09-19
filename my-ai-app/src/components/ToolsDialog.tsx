import { useEffect, useRef, type ReactNode } from 'react';
import { Icon } from './Icon';
export function ToolsDialog({ open, onClose, children }: { open: boolean; onClose(): void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = dialog.current;
    if (open && !node?.open) node?.showModal();
    if (!open && node?.open) node.close();
  }, [open]);
  return <dialog ref={dialog} id="companion-tools" className="tools-dialog" aria-labelledby="tools-title" onClose={onClose} onClick={(event) => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}>
    <header className="tools-heading"><div><span className="eyebrow">KHÔNG GIAN CỦA BẠN</span><h2 id="tools-title">Công cụ</h2></div><button type="button" autoFocus className="round-button" aria-label="Đóng công cụ" onClick={onClose}><Icon name="close" /></button></header>
    <div className="tools-content">{children}</div>
  </dialog>;
}
