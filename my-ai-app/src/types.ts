export interface Memory {
  id: number;
  user_id: string;
  memory_type: string;
  fact: string;
}

export interface UserProfile {
  user_id: string;
  username: string;
  affection_level: number;
  mood: string;
  interaction_count: number;
  last_interaction: string | null;
}

export interface MoodTimelineEntry {
  user_id: string;
  username: string;
  mood: string;
  affection_level: number;
  created_at: string | null;
}

export interface ReminderNotification {
  id: number;
  title: string;
  scheduled_for: string | null;
  note: string;
  message: string;
  done: boolean;
}

export interface ChatTiming {
  routing_ms?: number;
  generation_path?: string;
  first_token_ms?: number | null;
  total_llm_ms?: number;
  tokens_per_second?: number | null;
}

export interface ChatStreamPayload {
  search?: { status: string; source_count: number; unknown_dates?: number } | null;
  reply_vi?: string;
  motion?: string;
  expression?: string;
  response_mode?: string;
  due_reminders?: ReminderNotification[];
  timing?: ChatTiming;
  text?: string;
  provider?: string;
  message?: string;
}


export type ChatInputSource = "text" | "microphone";
export interface AvatarHandle {
  play: (plan: import('./avatar/reaction').ReactionPlan) => void;
  reset: () => void;
}
