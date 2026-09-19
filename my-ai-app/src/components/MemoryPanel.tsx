import type { useMemories } from '../hooks/useMemories';
interface Props { memory: ReturnType<typeof useMemories>; disabled: boolean; }
export function MemoryPanel({ memory, disabled: isLoading }: Props) {
  const { memories, memoryError, editingMemory, setEditingMemory, memoryDraft, setMemoryDraft, savingMemory, isLoadingMemories, loadMemories, handleDeleteMemory, handleEditMemory } = memory;
  return (
          <section className="memory-panel" aria-labelledby="memory-heading">
            <div className="memory-panel__header"><div><strong id="memory-heading">Bộ nhớ của bạn</strong><span>{memories.length} thông tin đang được giữ</span></div><button type="button" className="memory-refresh" onClick={() => void loadMemories()} disabled={isLoadingMemories} title="Tải lại memory">{isLoadingMemories ? '...' : '↻'}</button></div>
            {memoryError && <div className="memory-error">{memoryError}</div>}
            <p className="memory-empty">Bạn có thể sửa hoặc xóa điều Huohuo nhớ. Hội thoại cũ sẽ không được dùng làm ngữ cảnh sau khi thay đổi bộ nhớ.</p>
            {memories.length > 0 ? <ul className="memory-list">{memories.map((memory) => <li key={memory.id} className="memory-item">
              {editingMemory === memory.id ? <form className="memory-edit" onSubmit={(event) => { event.preventDefault(); void handleEditMemory(); }}>
                <textarea aria-label="Thông tin cần nhớ" value={memoryDraft} maxLength={2000} onChange={(event) => setMemoryDraft(event.target.value)} disabled={savingMemory} />
                <button type="submit" disabled={savingMemory || isLoading || !memoryDraft.trim()}>Lưu</button>
                <button type="button" disabled={savingMemory} onClick={() => setEditingMemory(null)}>Hủy</button>
              </form> : <><span>{memory.fact}</span>
                <button type="button" disabled={isLoading || savingMemory} onClick={() => { setEditingMemory(memory.id); setMemoryDraft(memory.fact); }}>Sửa</button>
                <button type="button" className="memory-delete" disabled={isLoading || savingMemory} onClick={() => void handleDeleteMemory(memory.id)} title="Xóa memory" aria-label={`Xóa memory: ${memory.fact}`}>×</button></>}
            </li>)}</ul> : !memoryError && <p className="memory-empty">Chưa có thông tin dài hạn nào.</p>}
          </section>
);
}
