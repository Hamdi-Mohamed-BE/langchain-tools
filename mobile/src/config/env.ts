const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_YOUTUBE_API_KEY = "";

export function normalizeBaseUrl(input: string): string {
  return input.trim().replace(/\/$/, "");
}

export function toWebSocketUrl(baseUrl: string): string {
  const normalized = normalizeBaseUrl(baseUrl);
  if (normalized.startsWith("https://")) {
    return normalized.replace("https://", "wss://") + "/chat/ws";
  }
  if (normalized.startsWith("http://")) {
    return normalized.replace("http://", "ws://") + "/chat/ws";
  }
  return `ws://${normalized}/chat/ws`;
}

export function getDefaultApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_BASE_URL;
  return normalizeBaseUrl(fromEnv || DEFAULT_API_BASE_URL);
}

const ENV = {
  API_BASE_URL: getDefaultApiBaseUrl(),
  YOUTUBE_API_KEY: String(process.env.EXPO_PUBLIC_YOUTUBE_API_KEY || DEFAULT_YOUTUBE_API_KEY),
};

export default ENV;
