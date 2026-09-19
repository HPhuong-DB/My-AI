import { useCallback, useEffect, useState } from 'react';
import { requestJSON, USER_ID } from '../api/client';
import type { Memory, UserProfile, MoodTimelineEntry } from '../types';
interface MemoryResponse { memories: Memory[]; profile: UserProfile | null; mood_timeline: MoodTimelineEntry[]; }
export function useMemories() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [moodTimeline, setMoodTimeline] = useState<MoodTimelineEntry[]>([]);
  const [memoryError, setMemoryError] = useState("");
  const [editingMemory, setEditingMemory] = useState<number | null>(null);
  const [memoryDraft, setMemoryDraft] = useState("");
  const [savingMemory, setSavingMemory] = useState(false);
  const [isLoadingMemories, setIsLoadingMemories] = useState(false);
  const loadMemories = useCallback(async () => {
    setIsLoadingMemories(true);
    setMemoryError("");
    try {
      const data = await requestJSON<MemoryResponse>(
        `/api/memories?user_id=${encodeURIComponent(USER_ID)}`,
        {},
        10_000,
      );

      setMemories(data.memories ?? []);
      setUserProfile(data.profile ?? null);
      setMoodTimeline(data.mood_timeline ?? []);
    } catch (error) {
      console.error("Không thể tải memory:", error);
      setMemoryError("Không thể tải bộ nhớ cá nhân.");
    } finally {
      setIsLoadingMemories(false);
    }
  }, []);

  const handleDeleteMemory = useCallback(async (memoryId: number) => {
    setSavingMemory(true);
    setMemoryError("");
    try {
      await requestJSON(
        `/api/memories/${memoryId}?user_id=${encodeURIComponent(USER_ID)}`,
        { method: "DELETE" },
        10_000,
      );
      setMemoryError("");
      await loadMemories();
    } catch (error) {
      console.error("Không thể xóa memory:", error);
      setMemoryError("Không thể xóa memory này.");
    } finally {
      setSavingMemory(false);
    }
  }, [loadMemories]);

  const handleEditMemory = async () => {
    if (editingMemory === null || !memoryDraft.trim()) return;
    setSavingMemory(true);
    setMemoryError("");
    try {
      await requestJSON(`/api/memories/${editingMemory}?user_id=${encodeURIComponent(USER_ID)}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fact: memoryDraft.trim() }),
      }, 10_000);
      setEditingMemory(null);
      await loadMemories();
    } catch (error) {
      setMemoryError(error instanceof Error ? error.message : 'Không thể sửa bộ nhớ.');
    } finally { setSavingMemory(false); }
  };

  useEffect(() => { const timer = window.setTimeout(() => void loadMemories(), 0); return () => window.clearTimeout(timer); }, [loadMemories]);
  return { memories, userProfile, moodTimeline, memoryError, editingMemory, setEditingMemory, memoryDraft, setMemoryDraft, savingMemory, isLoadingMemories, loadMemories, handleDeleteMemory, handleEditMemory };
}
