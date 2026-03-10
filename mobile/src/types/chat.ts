export type ChatRole = "user" | "assistant" | "tool" | "system";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
};

export type WebSocketEventPayload =
  | { type: "status"; text: string }
  | { type: "tool"; tool: string; text: string }
  | {
      type: "usage";
      model: string;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      estimated_cost_usd: number;
      currency: string;
      is_estimate: boolean;
    }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; text: string };
