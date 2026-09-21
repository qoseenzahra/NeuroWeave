export type InteractionMode = 'chat' | 'task';

export type ConversationListItem = {
  workspace_id?: string | null;
  conversation_id: string;
  title: string;
  archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string;
  last_message_role?: 'user' | 'assistant' | null;
};

export type ConversationPage = {
  conversations: ConversationListItem[];
  next_cursor: string | null;
  has_more: boolean;
};

export type StoredConversationMessage = {
  message_id: number;
  sequence: number;
  role: 'user' | 'assistant';
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ConversationSnapshot = {
  conversation: {
    workspace_id?: string | null;
    conversation_id: string;
    title: string;
    archived: boolean;
    created_at: string;
    updated_at: string;
  };
  messages: StoredConversationMessage[];
  has_more?: boolean;
  before_sequence?: number | null;
  context?: Record<string, unknown>;
};
