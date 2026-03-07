const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const userIdInput = document.getElementById("user-id");
const messageInput = document.getElementById("message");
const loadWorkoutBtn = document.getElementById("load-workout");
const loadChatsBtn = document.getElementById("load-chats");
const workoutOutput = document.getElementById("workout-output");
const themeToggle = document.getElementById("theme-toggle");
const costInputTokens = document.getElementById("cost-input-tokens");
const costOutputTokens = document.getElementById("cost-output-tokens");
const costTotalTokens = document.getElementById("cost-total-tokens");
const costUsd = document.getElementById("cost-usd");
const costModel = document.getElementById("cost-model");

const sessionUsage = {
  inputTokens: 0,
  outputTokens: 0,
  totalTokens: 0,
  usd: 0,
  model: "N/A",
  records: 0,
  scope: "system",
};

initTheme();
renderSessionUsage();
preloadChatHistory();
refreshUsageSummary();

function appendMessage(role, text) {
  const el = document.createElement("div");
  const roleTone = {
    user: "border-pine/35 bg-pine/10 dark:border-emerald-700 dark:bg-emerald-950/35",
    assistant: "border-clay/30 bg-clay/10 dark:border-orange-700 dark:bg-orange-950/30",
    tool: "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/25",
  };
  el.className = `mb-3 rounded-xl border px-3 py-2 sm:px-4 sm:py-3 ${roleTone[role] || "border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900"}`;

  const roleEl = document.createElement("div");
  roleEl.className = "mb-1 font-mono text-[11px] uppercase tracking-[0.16em] text-zinc-600 dark:text-zinc-300";
  roleEl.textContent = role;

  const bodyEl = document.createElement("div");
  bodyEl.className = "whitespace-pre-wrap text-sm leading-relaxed text-ink dark:text-zinc-100";

  el.appendChild(roleEl);
  el.appendChild(bodyEl);
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  const ref = { el, bodyEl, role, rawText: "" };
  setMessageBody(ref, text);
  return ref;
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const userId = Number(userIdInput.value);
  const message = messageInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  messageInput.value = "";

  const assistantMsg = appendMessage("assistant", "");
  const url = `/chat/stream?user_id=${encodeURIComponent(userId)}&message=${encodeURIComponent(message)}`;
  const stream = new EventSource(url);

  stream.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "status") {
      assistantMsg.rawText = payload.text;
      assistantMsg.bodyEl.textContent = payload.text;
      return;
    }
    if (payload.type === "tool") {
      appendMessage("tool", `[tool:${payload.tool}] ${payload.text}`);
      return;
    }
    if (payload.type === "usage") {
      void refreshUsageSummary();
      return;
    }
    if (payload.type === "token") {
      assistantMsg.rawText = `${assistantMsg.rawText || ""}${payload.text}`;
      assistantMsg.bodyEl.textContent = assistantMsg.rawText;
      return;
    }
    if (payload.type === "done") {
      setMessageBody(assistantMsg, assistantMsg.rawText || assistantMsg.bodyEl.textContent);
      stream.close();
      void refreshDataAfterResponse();
    }
  };

  stream.onerror = () => {
    assistantMsg.bodyEl.textContent = "Streaming failed. Check backend logs.";
    stream.close();
  };
});

loadWorkoutBtn.addEventListener("click", async () => {
  await loadLatestWorkout();
});

loadChatsBtn?.addEventListener("click", () => {
  preloadChatHistory();
});

userIdInput?.addEventListener("change", () => {
  preloadChatHistory();
  void loadLatestWorkout();
});

async function refreshDataAfterResponse() {
  await Promise.allSettled([
    refreshUsageSummary(),
    loadLatestWorkout(),
  ]);
}

async function loadLatestWorkout() {
  const userId = Number(userIdInput.value);
  if (!userId || userId < 1) {
    return;
  }

  try {
    const response = await fetch(`/workouts/latest?user_id=${encodeURIComponent(userId)}`);
    if (!response.ok) {
      workoutOutput.textContent = "No workout plan found for this user yet.";
      return;
    }
    const data = await response.json();
    renderWorkout(data);
  } catch (_error) {
    workoutOutput.textContent = "Could not refresh workout data.";
  }
}

function renderWorkout(payload) {
  workoutOutput.innerHTML = "";

  const plan = payload?.plan;
  if (!plan || !Array.isArray(plan.weekly_plan)) {
    const empty = document.createElement("div");
    empty.className = "rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200";
    empty.textContent = "No valid workout plan payload to render.";
    workoutOutput.appendChild(empty);
    return;
  }

  const summary = document.createElement("div");
  summary.className = "mb-4 rounded-xl border border-zinc-200 bg-gradient-to-r from-zinc-50 to-orange-50 p-3 dark:border-zinc-700 dark:from-zinc-900 dark:to-zinc-800";
  summary.innerHTML = `
    <p class="font-mono text-[11px] uppercase tracking-[0.16em] text-zinc-600 dark:text-zinc-300">Plan Summary</p>
    <p class="mt-1 text-sm text-ink dark:text-zinc-100"><span class="font-semibold">Goal:</span> ${escapeText(plan.goal || "N/A")}</p>
    <p class="text-sm text-ink dark:text-zinc-100"><span class="font-semibold">Days/Week:</span> ${escapeText(String(plan.days_per_week ?? "N/A"))}</p>
  `;
  workoutOutput.appendChild(summary);

  for (const day of plan.weekly_plan) {
    const dayCard = document.createElement("section");
    dayCard.className = "mb-3 rounded-2xl border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900 sm:p-4";

    const titleWrap = document.createElement("div");
    titleWrap.className = "mb-3 flex flex-wrap items-center justify-between gap-2";
    titleWrap.innerHTML = `
      <h3 class="font-display text-lg font-bold text-ink dark:text-zinc-100">${escapeText(day.title || "Workout Day")}</h3>
      <span class="rounded-full bg-pine/10 px-3 py-1 text-xs font-semibold text-pine dark:bg-emerald-950/60 dark:text-emerald-300">${escapeText(day.focus || "General")}</span>
    `;
    dayCard.appendChild(titleWrap);

    const list = document.createElement("div");
    list.className = "space-y-3";

    for (const exercise of day.exercises || []) {
      const item = document.createElement("article");
      item.className = "rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800";

      const name = escapeText(exercise.name || "Exercise");
      const sets = escapeText(exercise.sets || "?");
      const reps = escapeText(exercise.reps || "?");

      item.innerHTML = `
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p class="text-sm font-semibold text-ink dark:text-zinc-100">${name}</p>
          <span class="rounded-md bg-white px-2 py-1 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">${sets} x ${reps}</span>
        </div>
      `;

      if (exercise.video_url) {
        const videoWrap = document.createElement("div");
        videoWrap.className = "mt-2";

        const youtubeEmbedUrl = buildYouTubeEmbedUrl(exercise.video_url);

        if (youtubeEmbedUrl) {
          const frame = document.createElement("iframe");
          frame.className = "aspect-video w-full rounded-lg border border-zinc-300 bg-black";
          frame.src = youtubeEmbedUrl;
          frame.title = `${name} video`;
          frame.loading = "lazy";
          frame.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
          frame.referrerPolicy = "strict-origin-when-cross-origin";
          frame.allowFullscreen = true;
          videoWrap.appendChild(frame);
        } else {
          const video = document.createElement("video");
          video.className = "w-full rounded-lg border border-zinc-300 bg-black";
          video.controls = true;
          video.preload = "metadata";
          video.playsInline = true;
          video.src = exercise.video_url;
          videoWrap.appendChild(video);
        }

        const fallback = document.createElement("a");
        fallback.className = "mt-2 inline-block text-xs font-semibold text-pine underline hover:text-pineDark dark:text-emerald-300";
        fallback.href = exercise.video_url;
        fallback.target = "_blank";
        fallback.rel = "noopener noreferrer";
        fallback.textContent = "Open video in new tab";

        videoWrap.appendChild(fallback);
        item.appendChild(videoWrap);
      }

      list.appendChild(item);
    }

    dayCard.appendChild(list);
    workoutOutput.appendChild(dayCard);
  }
}

async function preloadChatHistory() {
  const userId = Number(userIdInput.value);
  if (!userId || userId < 1) {
    return;
  }

  try {
    const response = await fetch(`/chat/history?user_id=${encodeURIComponent(userId)}&limit=60`);
    if (!response.ok) {
      appendMessage("assistant", "Could not load chat history for this user.");
      return;
    }

    const items = await response.json();
    chatLog.innerHTML = "";
    for (const item of items) {
      if (!item || !item.role) continue;
      appendMessage(item.role, item.content || "");
    }
    if (!items.length) {
      appendMessage("assistant", "No chat history found for this user yet.");
    }
  } catch (_error) {
    appendMessage("assistant", "Network error while loading chat history.");
  }
}

function initTheme() {
  const stored = localStorage.getItem("gym-ui-theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const mode = stored || (prefersDark ? "dark" : "light");
  applyTheme(mode);

  themeToggle?.addEventListener("click", () => {
    const isDark = document.documentElement.classList.contains("dark");
    applyTheme(isDark ? "light" : "dark");
  });
}

function applyTheme(mode) {
  const dark = mode === "dark";
  document.documentElement.classList.toggle("dark", dark);
  localStorage.setItem("gym-ui-theme", dark ? "dark" : "light");
  if (themeToggle) {
    themeToggle.value = dark ? "Day" : "Night";
    themeToggle.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  }
}

function updateSessionUsage(payload) {
  sessionUsage.inputTokens = Number(payload.input_tokens || 0);
  sessionUsage.outputTokens = Number(payload.output_tokens || 0);
  sessionUsage.totalTokens = Number(payload.total_tokens || 0);
  sessionUsage.usd = Number(payload.estimated_cost_usd || 0);
  sessionUsage.model = payload.model || sessionUsage.model;
  sessionUsage.records = Number(payload.records || sessionUsage.records || 0);
  sessionUsage.scope = payload.scope || sessionUsage.scope;
  renderSessionUsage();
}

async function refreshUsageSummary() {
  try {
    const response = await fetch("/chat/usage/summary");
    if (!response.ok) {
      return;
    }
    const summary = await response.json();
    updateSessionUsage(summary);
  } catch (_error) {
    // Keep current UI values if the summary request fails.
  }
}

function renderSessionUsage() {
  if (costInputTokens) costInputTokens.textContent = formatInt(sessionUsage.inputTokens);
  if (costOutputTokens) costOutputTokens.textContent = formatInt(sessionUsage.outputTokens);
  if (costTotalTokens) costTotalTokens.textContent = formatInt(sessionUsage.totalTokens);
  if (costUsd) costUsd.textContent = formatUsd(sessionUsage.usd);
  if (costModel) {
    const scopeLabel = sessionUsage.scope === "user" ? "User" : "System";
    costModel.textContent = `${scopeLabel} total | records: ${formatInt(sessionUsage.records)} | model: ${sessionUsage.model} (estimated)`;
  }
}

function formatInt(value) {
  return Number(value || 0).toLocaleString();
}

function formatUsd(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 6,
    maximumFractionDigits: 6,
  }).format(Number(value || 0));
}

function escapeText(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setMessageBody(messageRef, text) {
  const content = text || "";
  messageRef.rawText = content;

  if (messageRef.role === "assistant") {
    messageRef.bodyEl.innerHTML = formatRichText(content);
    return;
  }

  if (messageRef.role === "tool") {
    messageRef.bodyEl.innerHTML = formatToolText(content);
    return;
  }

  messageRef.bodyEl.innerHTML = escapeText(content).replaceAll("\n", "<br>");
}

function formatToolText(text) {
  const safe = escapeText(text).replaceAll("\n", " ");
  return `<span class="font-mono text-xs">${safe}</span>`;
}

function formatRichText(text) {
  const normalized = String(text || "")
    .replaceAll("\r\n", "\n")
    .replace(/\*{3,}/g, "**")
    .trim();

  if (!normalized) {
    return "";
  }

  const lines = normalized.split("\n");
  const chunks = [];
  let listItems = [];

  const flushList = () => {
    if (!listItems.length) return;
    chunks.push(`<ul class="ml-5 list-disc space-y-1">${listItems.join("")}</ul>`);
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)/);
    if (bullet) {
      listItems.push(`<li>${formatInlineMarkdown(bullet[1])}</li>`);
      continue;
    }

    flushList();
    chunks.push(`<p class="mb-1">${formatInlineMarkdown(line)}</p>`);
  }

  flushList();
  return chunks.join("");
}

function formatInlineMarkdown(text) {
  let safe = escapeText(text);
  safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  safe = safe.replace(/`([^`]+)`/g, '<code class="rounded bg-zinc-200 px-1 py-0.5 text-xs dark:bg-zinc-700">$1</code>');
  safe = safe.replace(/(Day\s+\d+\s*:?)/gi, "<strong>$1</strong>");
  return safe;
}

function buildYouTubeEmbedUrl(url) {
  const info = parseYouTubeVideo(url);
  if (!info?.id) return null;

  const params = new URLSearchParams({
    rel: "0",
    modestbranding: "1",
    playsinline: "1",
  });
  if (info.startSeconds > 0) {
    params.set("start", String(info.startSeconds));
  }
  return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(info.id)}?${params.toString()}`;
}

function parseYouTubeVideo(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    let id = null;

    if (host === "youtu.be") {
      id = parsed.pathname.replace(/^\//, "") || null;
    }
    if (!id && (host === "youtube.com" || host === "www.youtube.com" || host === "m.youtube.com")) {
      if (parsed.pathname === "/watch") {
        id = parsed.searchParams.get("v");
      }
      if (parsed.pathname.startsWith("/shorts/")) {
        id = parsed.pathname.split("/").filter(Boolean)[1] || null;
      }
      if (parsed.pathname.startsWith("/embed/")) {
        id = parsed.pathname.split("/").filter(Boolean)[1] || null;
      }
    }

    const startSeconds = parseYouTubeStartSeconds(parsed.searchParams.get("t") || parsed.searchParams.get("start"));
    return id ? { id, startSeconds } : null;
  } catch (_error) {
    return null;
  }
}

function parseYouTubeStartSeconds(value) {
  if (!value) return 0;
  if (/^\d+$/.test(value)) return Number(value);

  const parts = value.match(/(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?/i);
  if (!parts) return 0;
  const hours = Number(parts[1] || 0);
  const minutes = Number(parts[2] || 0);
  const seconds = Number(parts[3] || 0);
  return (hours * 3600) + (minutes * 60) + seconds;
}

