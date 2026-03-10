import { normalizeBaseUrl } from "../config/env";
import { AuthResponse } from "../types/auth";

const AUTH_REQUEST_TIMEOUT_MS = 15000;

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch (_error) {
    // Fall through to generic message when backend body is not JSON.
  }
  return `Request failed with status ${response.status}`;
}

async function postAuth(baseUrl: string, path: string, email: string, password: string): Promise<AuthResponse> {
  const target = `${normalizeBaseUrl(baseUrl)}${path}`;
  let response: Response;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), AUTH_REQUEST_TIMEOUT_MS);

  try {
    response = await fetch(target, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
        password,
      }),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(
        "Request timed out after 15s. Check API URL/server and try again.",
      );
    }
    throw new Error(
      "Network request failed. Check API URL and backend reachability. " +
        `Current URL: ${normalizeBaseUrl(baseUrl)}. ` +
        "If using a real phone, use your PC LAN IP (not 127.0.0.1) and run backend with a LAN-reachable host.",
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return (await response.json()) as AuthResponse;
}

export function signupWithEmail(baseUrl: string, email: string, password: string): Promise<AuthResponse> {
  return postAuth(baseUrl, "/auth/register", email, password);
}

export function loginWithEmail(baseUrl: string, email: string, password: string): Promise<AuthResponse> {
  return postAuth(baseUrl, "/auth/login", email, password);
}
