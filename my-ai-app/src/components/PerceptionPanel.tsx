import type { usePerception } from '../hooks/usePerception';
type Model = ReturnType<typeof usePerception>;

export function PerceptionControls({ model, disabled }: { model: Model; disabled: boolean }) {
  const { fileInputRef, documentFileInputRef } = model;
  return <>
    <button onClick={() => model.fileInputRef.current?.click()} disabled={disabled} className="action-button action-button--secondary action-button--compact">📷 OCR</button>
    <button onClick={() => void model.handleScreenCapture()} disabled={disabled || !!window.huohuoDesktop} title={window.huohuoDesktop ? 'Chụp màn hình hiện dùng trên bản web' : 'Chọn màn hình để đọc'} className="action-button action-button--secondary action-button--compact">{model.isCapturingScreen ? 'Đang đọc…' : '🖥️ Màn hình'}</button>
    <button onClick={() => model.documentFileInputRef.current?.click()} disabled={disabled} className="action-button action-button--secondary action-button--compact">{model.isReadingDocument ? 'Đang đọc…' : '📄 Tài liệu'}</button>
    {model.selectedImageName && <button onClick={() => void model.handleImageComment()} disabled={disabled} className="action-button action-button--secondary action-button--compact">🤖 AI nhận xét</button>}
    <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={(event) => void model.handleOcrFile(event.target.files?.[0] || null)} />
    <input ref={documentFileInputRef} type="file" accept=".txt,.md,.csv,.pdf,.docx" hidden onChange={(event) => void model.handleDocumentFile(event.target.files?.[0] || null)} />
  </>;
}

export function PerceptionResults({ model }: { model: Model }) {
  return <>
    {model.ocrResult && <div className="ocr-panel"><strong>OCR Result:</strong><p>{model.ocrResult}</p></div>}
    {model.ocrError && <div className="ocr-error" role="alert">{model.ocrError}</div>}
    {model.imageComment && <div className="image-comment-panel"><strong>AI nhận xét:</strong><p>{model.imageComment}</p></div>}
    {model.imageCommentError && <div className="ocr-error" role="alert">{model.imageCommentError}</div>}
    {model.documentText && <div className="ocr-panel"><strong>Nội dung tài liệu:</strong><p>{model.documentText}</p></div>}
    {model.documentError && <div className="ocr-error" role="alert">{model.documentError}</div>}
    {model.status && <p className="helper-text">{model.status}</p>}
    {model.timing && <p className="timing-text">{model.timing}</p>}
  </>;
}
