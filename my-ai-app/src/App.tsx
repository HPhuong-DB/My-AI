import { lazy, Suspense, useCallback, useRef, useState } from 'react';
import './App.css';
import { API_BASE_URL, requestJSON, setPrivacyConsent } from './api/client';
import { ServiceStatus } from './SessionPanels';
import { ToolsDialog } from './components/ToolsDialog';
import { Icon } from './components/Icon';
import { ChatComposer } from './components/ChatComposer';
import { MemoryPanel } from './components/MemoryPanel';
import { PerceptionControls, PerceptionResults } from './components/PerceptionPanel';
import { ReminderPanel } from './components/ReminderPanel';
import { useActivity } from './hooks/useActivity';
import { useAgentEvents } from './hooks/useAgentEvents';
import { useBubble } from './hooks/useBubble';
import { useChat } from './hooks/useChat';
import { useMemories } from './hooks/useMemories';
import { useMicrophone } from './hooks/useMicrophone';
import { usePerception } from './hooks/usePerception';
import { useReminders } from './hooks/useReminders';
import type { AvatarHandle, ChatStreamPayload } from './types';
import { planReaction } from './avatar/reaction';
import { useProactive } from './hooks/useProactive';

const AvatarStage = lazy(() => import('./components/AvatarStage'));

export default function App() {
  const avatar = useRef<AvatarHandle>(null);
  const presentationBlocked = useRef(false);
  const activity = useActivity();
  const bubble = useBubble();
  const { show, hide } = bubble;
  const hideSpeech = useCallback(() => { avatar.current?.reset(); hide(); }, [hide]);
  const showNotice = useCallback((text: string, duration?: number) => {
    avatar.current?.reset(); show(text, duration);
  }, [show]);
  const presentReply = useCallback((text: string) => {
    if (presentationBlocked.current) return;
    const plan = planReaction(text);
    show(plan.text, plan.displayMs);
    avatar.current?.play(plan);
  }, [show]);
  const memory = useMemories();
  const proactive = useProactive();
  const { refresh: refreshProactive } = proactive;
  const reminders = useReminders(showNotice);
  const { loadMemories } = memory;
  const { setReminders } = reminders;
  const onReply = useCallback((reply: ChatStreamPayload) => {
    presentReply(reply.reply_vi || '');
    void loadMemories();
    if (reply.due_reminders?.length) setReminders(reply.due_reminders);
  }, [loadMemories, setReminders, presentReply]);
  const chat = useChat({ activity, show, hide: hideSpeech, onReply, onSettled: refreshProactive });
  const perception = usePerception(activity, chat.updateDraft);
  const microphone = useMicrophone(chat.send);
  const [toolsOpen, setToolsOpen] = useState(false);
  const closeTools = useCallback(() => setToolsOpen(false), []);
  const [pinned, setPinned] = useState(true);
  const desktop = window.huohuoDesktop;
  const [windowError, setWindowError] = useState('');
  const openCompanion = () => {
    const url = new URL(window.location.href);
    url.searchParams.set('companion', '1');
    const child = window.open(url, 'huohuo-companion', 'popup,width=440,height=680');
    if (!child) setWindowError('Trình duyệt đang chặn cửa sổ riêng. Cho phép cửa sổ bật lên rồi thử lại nhé.');
    else { child.focus(); setWindowError(''); }
  };
  const [stopped, setStopped] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [safetyError, setSafetyError] = useState('');
  useAgentEvents(perception.onEvent, presentReply, activity.busyRef, {
    typing: !!chat.inputText.trim(), reading: bubble.visible, listening: microphone.isListening,
    paused: stopped || !proactive.settings?.enabled || proactive.saving,
  }, reminders.refresh, chat.refreshHistory);

  const toggleStop = async () => {
    setStopping(true); setSafetyError('');
    if (!stopped) {
      presentationBlocked.current = true;
      activity.block(true);
      chat.cancel(); microphone.stop(); perception.cancel();
      hideSpeech();
      setStopped(true);
      void setPrivacyConsent('screen', false);
    }
    try {
      await requestJSON(stopped ? '/api/agent/resume' : '/api/agent/emergency-stop', { method: 'POST' }, 10_000);
      if (stopped) { presentationBlocked.current = false; activity.block(false); setStopped(false); }
    } catch {
      setSafetyError('Đã dừng thao tác trên trình duyệt, nhưng chưa xác nhận được trạng thái agent trên máy chủ.');
    } finally { setStopping(false); }
  };
  const disabled = activity.isBusy || stopped;

  return <div className="app-shell"><div className="app-card">
    <header className={`app-header ${desktop ? 'desktop-drag' : ''}`}>
      <div className="brand"><span className="brand-mark">✦</span><div><h1>Huohuo</h1><span className="eyebrow">Một góc nhỏ để chuyện trò</span></div></div>
      <div className="status-pill" role="status"><span className={`status-dot ${microphone.isListening ? 'status-dot--listening' : ''}`} />
        {stopped ? 'Đã tạm dừng' : microphone.isListening ? 'Đang nghe' : activity.isBusy ? 'Đang nghĩ…' : 'Ở đây cùng bạn'}
      </div>
      {desktop && <div className="desktop-actions"><button type="button" className="round-button" title="Thu nhỏ" aria-label="Thu nhỏ cửa sổ" onClick={() => void desktop.minimize()}>−</button><button type="button" className="round-button" title="Đóng" aria-label="Đóng cửa sổ" onClick={() => void desktop.close()}><Icon name="close" /></button></div>}
    </header>
    <main className="stage-area" aria-label="Nhân vật Huohuo"><div className="scene-panel">
      <div className="scene-glow" /><div className="scene-orbit" aria-hidden="true" />
      {bubble.visible && <div className="chat-bubble" role="status">{bubble.text}</div>}
      <Suspense fallback={<p className="stage-loading" role="status">Đang tải Huohuo…</p>}><AvatarStage ref={avatar} /></Suspense>
      <span className="stage-caption" aria-hidden="true">HUOHUO · YOUR LITTLE COMPANION</span>
    </div></main>
    <footer className="control-panel">
      <ChatComposer chat={chat} microphone={microphone} disabled={disabled} toolsOpen={toolsOpen} openTools={() => setToolsOpen(true)} />
      <div className="composer-caption" role="status">{stopped ? 'Huohuo đang tạm dừng. Mở Công cụ để tiếp tục.' : microphone.isListening || microphone.status !== 'Nhấn mic để nói chuyện' ? microphone.status : 'Nhắn một câu, hoặc nhấn micro để nói.'}</div>
      {safetyError && <p className="inline-error" role="alert">{safetyError}</p>}
    </footer>
    <ToolsDialog open={toolsOpen} onClose={closeTools}>
      <section className="tool-section"><h3>Nhìn & đọc</h3><div className="tool-actions"><PerceptionControls model={perception} disabled={disabled} /></div><PerceptionResults model={perception} /></section>
      <section className="tool-section"><h3>Đồng hành</h3>
        <label className="setting-row"><span>Chủ động bắt chuyện<small>Huohuo sẽ chọn lúc phù hợp để nói.</small></span><input type="checkbox" checked={!!proactive.settings?.enabled} disabled={!proactive.settings || proactive.saving}
          onChange={(event) => { if (!event.target.checked) hideSpeech(); void proactive.toggle(event.target.checked); }} /></label>
        {proactive.error && <p role="alert">{proactive.error}</p>}
        {!desktop && <button type="button" className="tool-row" onClick={openCompanion}><Icon name="window" /><span>Mở cửa sổ riêng<small>Đưa Huohuo sang một cửa sổ nhỏ.</small></span></button>}
        {desktop && <label className="setting-row desktop-pin"><span>Luôn nổi trên ứng dụng khác</span><input type="checkbox" checked={pinned} onChange={(event) => { void desktop.setPinned(event.target.checked).then(setPinned).catch(() => setWindowError('Chưa thay đổi được chế độ ghim.')); }} /></label>}
        {windowError && <p className="inline-error" role="alert">{windowError}</p>}
        <button type="button" onClick={() => void toggleStop()} disabled={stopping} className="tool-row stop-control"><Icon name="stop" /><span>{stopped ? 'Tiếp tục hoạt động' : 'Tạm dừng mọi hoạt động'}</span></button>
      </section>
      <ReminderPanel model={reminders} />
      <MemoryPanel memory={memory} disabled={activity.isBusy} />
      <details className="tool-section diagnostics"><summary>Kết nối & thời gian phản hồi</summary><ServiceStatus apiUrl={API_BASE_URL} />{chat.timing && <p className="timing-text">{chat.timing}</p>}</details>
    </ToolsDialog>
  </div></div>;
}
