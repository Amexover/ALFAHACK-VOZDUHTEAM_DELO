export type Intent =
  "chat" | "rating" | "advice" | "news" | "application_review" | "draft_reply";
export interface AssistantConfig {
  enabled: boolean;
  model: string;
  audience: "client" | "staff";
  intents: Intent[];
  max_message_characters: number;
  streaming: boolean;
  suggestions: string[];
}
export interface Source {
  id: string;
  title: string;
  kind: string;
  url: string | null;
  published_at: string | null;
  is_demo: boolean;
  excerpt: string;
}
export interface Conversation {
  id: string;
  audience: string;
  company_id: number | null;
  application_id: number | null;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface Turn {
  id: string;
  request_id: string;
  status: "pending" | "completed" | "failed";
  intent: Intent;
  user_content: string;
  assistant_content: string | null;
  sources: Source[];
  tool_calls: { name: string; ok: boolean }[];
  model: string;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
  latency_ms: number | null;
}
export interface Page<T> {
  items: T[];
  has_more: boolean;
}
export type StreamEvent =
  | { type: "start"; turn_id: string; model: string }
  | { type: "sources"; items: Source[] }
  | { type: "delta"; text: string }
  | { type: "tool"; name: string; ok: boolean }
  | { type: "done"; turn: Turn; replayed?: boolean }
  | {
      type: "error";
      code: string;
      message: string;
      status: number;
      turn_id?: string;
    };
export interface KnowledgeDocument {
  id: string;
  title: string;
  body: string;
  audience: "client" | "staff";
  kind: "knowledge" | "news";
  url: string | null;
  published_at: string | null;
  is_demo: boolean;
}
