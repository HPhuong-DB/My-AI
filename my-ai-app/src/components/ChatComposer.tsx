import type { useChat } from '../hooks/useChat';
import type { useMicrophone } from '../hooks/useMicrophone';
import { Icon } from './Icon';
interface Props {
  chat: ReturnType<typeof useChat>; microphone: ReturnType<typeof useMicrophone>;
  disabled: boolean; toolsOpen: boolean; openTools(): void;
}
export function ChatComposer({ chat, microphone, disabled, toolsOpen, openTools }: Props) {
  return <>
    <form className="composer" onSubmit={(event) => { event.preventDefault(); if (!disabled && !microphone.isListening) void chat.send(); }}>
      <button type="button" className={`round-button ${toolsOpen ? 'round-button--selected' : ''}`} onClick={openTools} aria-label="Mở công cụ" title="Công cụ" aria-expanded={toolsOpen} aria-controls="companion-tools"><Icon name="tools" /></button>
      <input value={chat.inputText} onChange={(event) => chat.updateDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); }} placeholder="Nói gì đó với Huohuo…" disabled={disabled || microphone.isListening} className="message-input" aria-label="Tin nhắn cho Huohuo" autoComplete="off" />
      <button type="button" onClick={() => void microphone.toggle()} disabled={disabled && !microphone.isListening} className={`round-button mic-button ${microphone.isListening ? 'round-button--listening' : ''}`} aria-label={microphone.isListening ? 'Dừng nghe' : 'Nói bằng microphone'} aria-pressed={microphone.isListening} title={microphone.isListening ? 'Dừng nghe' : 'Nói bằng microphone'}><Icon name={microphone.isListening ? 'stop' : 'mic'} /></button>
      <button type="submit" disabled={disabled || microphone.isListening || !chat.inputText.trim()} className="round-button send-button" aria-label="Gửi tin nhắn" title="Gửi"><Icon name="send" /></button>
    </form>
    {chat.error && <div className="inline-error" role="alert">{chat.error} <button type="button" disabled={disabled} onClick={() => void chat.send(chat.retryText)}>Thử lại</button></div>}
  </>;
}
