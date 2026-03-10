import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { MessageBubble } from "./src/components/MessageBubble";
import YouTubeShort from "./src/components/YouTubeShort";
import { getDefaultApiBaseUrl, normalizeBaseUrl, toWebSocketUrl } from "./src/config/env";
import { loginWithEmail, signupWithEmail } from "./src/services/authApi";
import { ChatSocketClient } from "./src/services/chatSocket";
import { AuthMode, UserSession } from "./src/types/auth";
import { ChatMessage, WebSocketEventPayload } from "./src/types/chat";
import { toYouTubeVideo } from "./src/utils/youtube";

const SESSION_STORAGE_KEY = "ai_gym_mobile_session_v1";

type WorkoutExerciseData = {
  name?: string;
  sets?: number;
  reps?: string;
  video_url?: string | null;
};

type WorkoutDayData = {
  title?: string;
  focus?: string;
  exercises?: WorkoutExerciseData[];
};

type WorkoutResponseData = {
  plan?: {
    goal?: string;
    days_per_week?: number;
    weekly_plan?: WorkoutDayData[];
    notes?: string;
  };
};

function makeId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function isLikelyEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function utf8ByteLength(value: string): number {
  return unescape(encodeURIComponent(value)).length;
}

/** Strip JSON payloads, signatures, tokens, and other sensitive data from a message. */
function sanitizeText(raw: string): string {
  let text = (raw ?? "").trim();
  if (!text) return "";

  // Remove fenced code blocks
  text = text.replace(/```[\s\S]*?```/g, "");

  // Remove JSON objects / arrays
  text = text.replace(/\{\s*"[\s\S]*?\}\s*/g, "");
  text = text.replace(/\[\s*\{[\s\S]*?\}\s*\]\s*/g, "");
  // Remove python-style dicts like [{'type': ...}]
  text = text.replace(/\[\s*\{'[\s\S]*?\}\s*\]\s*/g, "");

  // Remove residual JSON key:value fragments ("key": "value" or "key": 123)
  text = text.replace(/"[a-z_]+"\s*:\s*"[^"]*"/gi, "");
  text = text.replace(/"[a-z_]+"\s*:\s*\d+/gi, "");

  // Remove bracket/brace clusters and empty pairs ([], {}, [][], etc.)
  text = text.replace(/[\[\]{}]{2,}/g, "");
  text = text.replace(/\[\]/g, "");

  // Remove lines that are only structural JSON characters (commas, brackets, braces, spaces)
  text = text.replace(/^[\s,\[\]{}]+$/gm, "");

  // Remove inline runs of commas/brackets that have no letter content
  text = text.replace(/[,\s]*[\[\]{}][,\s\[\]{}]*/g, (m) =>
    /[a-zA-Z]/.test(m) ? m : "",
  );

  // Redact JWT tokens
  text = text.replace(/\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b/g, "[REDACTED]");
  // Redact API keys / secrets
  text = text.replace(/\bAIza[0-9A-Za-z_\-]{20,}\b/g, "[REDACTED]");
  text = text.replace(/\bsk-[A-Za-z0-9]{16,}\b/g, "[REDACTED]");
  // Redact key=value secrets
  text = text.replace(/(?:api[_-]?key|token|authorization|bearer|secret|password)\s*[:=]\s*['"]?[A-Za-z0-9_\-\.]{8,}['"]?/gi, "[REDACTED]");
  // Redact long base64 blobs (like signature fields)
  text = text.replace(/[A-Za-z0-9+/=]{80,}/g, "[REDACTED]");

  // Remove internal policy/tool lines and lines that became empty/only punctuation
  const kept = text.split("\n").filter((line) => {
    const low = line.trim().toLowerCase();
    if (low.startsWith("tools used:")) return false;
    if (low.startsWith("toolpolicy:")) return false;
    if (low.startsWith("safetypolicy:")) return false;
    if (low.startsWith("context:")) return false;
    // Drop lines that are only punctuation/whitespace after stripping
    if (!/[a-zA-Z]/.test(line)) return false;
    return true;
  });

  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}


export default function App() {
  const [activeView, setActiveView] = useState<"chat" | "workout">("chat");
  const [apiBaseUrl, setApiBaseUrl] = useState(getDefaultApiBaseUrl());
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [session, setSession] = useState<UserSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [messageText, setMessageText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [statusText, setStatusText] = useState("Disconnected");
  const [connected, setConnected] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showTypingDots, setShowTypingDots] = useState(false);
  const [workoutLoading, setWorkoutLoading] = useState(false);
  const [workoutData, setWorkoutData] = useState<WorkoutResponseData | null>(null);
  const [workoutError, setWorkoutError] = useState<string | null>(null);

  const scrollRef = useRef<ScrollView | null>(null);
  const socketRef = useRef<ChatSocketClient | null>(null);
  const activeAssistantId = useRef<string | null>(null);
  const authRef = useRef<{ accessToken: string | null; userId: number | null }>({ accessToken: null, userId: null });
  const pendingMessageRef = useRef<string | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const wsUrl = useMemo(() => toWebSocketUrl(apiBaseUrl), [apiBaseUrl]);

  useEffect(() => {
    authRef.current = {
      accessToken: session?.accessToken || null,
      userId: session?.userId || null,
    };
  }, [session]);

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  useEffect(() => {
    const loadSession = async () => {
      try {
        const raw = await AsyncStorage.getItem(SESSION_STORAGE_KEY);
        if (!raw) {
          return;
        }
        const parsed = JSON.parse(raw) as UserSession;
        if (!parsed || !parsed.userId || !parsed.accessToken) {
          return;
        }
        setSession(parsed);
        setEmail(parsed.email);
      } catch (_error) {
        // Ignore corrupted storage and proceed as logged out.
      } finally {
        setSessionLoading(false);
      }
    };

    void loadSession();
  }, []);

  useEffect(() => {
    const client = new ChatSocketClient({
      onOpen: () => {
        setConnected(true);
        setStatusText("Connected");

        const pending = pendingMessageRef.current;
        const token = authRef.current.accessToken;
        const userId = authRef.current.userId;
        if (pending && token) {
          const accepted = client.sendMessage(token, pending, userId || undefined);
          if (accepted) {
            pendingMessageRef.current = null;
          } else {
            addMessage("system", "Connected but failed to send pending message.");
          }
        }
      },
      onClose: () => {
        setConnected(false);
        setStatusText("Reconnecting...");
      },
      onError: (message) => {
        setStatusText(message);
      },
      onEvent: (payload) => {
        handleSocketEvent(payload);
      },
    });
    socketRef.current = client;

    return () => {
      clearReconnectTimer();
      client.close();
      socketRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const persistSession = async (value: UserSession | null) => {
    if (!value) {
      await AsyncStorage.removeItem(SESSION_STORAGE_KEY);
      return;
    }
    await AsyncStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(value));
  };

  const addMessage = (role: ChatMessage["role"], text: string): string => {
    const id = makeId(role);
    const cleaned = role === "user" ? text : sanitizeText(text);
    if (!cleaned && role !== "user") return id; // drop empty sanitized messages
    setMessages((prev) => [...prev, { id, role, text: cleaned }]);
    return id;
  };

  const updateMessage = (id: string, updater: (prev: string) => string) => {
    setMessages((prev) =>
      prev.map((item) => {
        if (item.id !== id) {
          return item;
        }
        return { ...item, text: updater(item.text) };
      }),
    );
  };

  const ensureAssistantMessage = (): string => {
    if (activeAssistantId.current) {
      return activeAssistantId.current;
    }
    // Create a blank placeholder directly — bypass sanitizeText which would
    // drop the empty message and prevent subsequent updateMessage calls.
    const newId = makeId("assistant");
    setMessages((prev) => [...prev, { id: newId, role: "assistant", text: "" }]);
    activeAssistantId.current = newId;
    return newId;
  };

  const handleSocketEvent = (payload: WebSocketEventPayload) => {
    if (payload.type === "status") {
      setStatusText(payload.text);
      if (payload.text === "Thinking...") {
        setShowTypingDots(true);
      }
      return;
    }

    if (payload.type === "tool") {
      // Tool events are internal — don't display them to the user.
      return;
    }

    if (payload.type === "usage") {
      // Usage data is available but intentionally not rendered in compact chat UI.
      return;
    }

    if (payload.type === "token") {
      setShowTypingDots(false);
      const id = ensureAssistantMessage();
      updateMessage(id, (prev) => `${prev}${payload.text}`);
      return;
    }

    if (payload.type === "error") {
      setShowTypingDots(false);
      addMessage("system", payload.text);
      activeAssistantId.current = null;
      setStatusText("Error");
      return;
    }

    if (payload.type === "done") {
      setShowTypingDots(false);
      // Run a final sanitize pass on the assembled assistant message.
      const doneId = activeAssistantId.current;
      if (doneId) {
        setMessages((prev) =>
          prev
            .map((m) => (m.id === doneId ? { ...m, text: sanitizeText(m.text) } : m))
            .filter((m) => m.text.length > 0),
        );
      }
      activeAssistantId.current = null;
      setStatusText("Ready");
    }
  };

  const connectSocket = () => {
    if (!session) {
      setStatusText("Please login first");
      return;
    }
    const normalized = normalizeBaseUrl(apiBaseUrl);
    setApiBaseUrl(normalized);
    setStatusText("Connecting...");
    socketRef.current?.connect(toWebSocketUrl(normalized));
  };

  const sendMessage = () => {
    const userId = session?.userId;
    const accessToken = session?.accessToken;
    const trimmed = messageText.trim();

    if (!accessToken) {
      setStatusText("Invalid authenticated user");
      return;
    }
    if (!trimmed) {
      return;
    }

    if (!connected) {
      pendingMessageRef.current = trimmed;
      addMessage("user", trimmed);
      setMessageText("");
      setStatusText("Connecting...");
      connectSocket();
      addMessage("system", "Connecting... your message will be sent automatically.");
      return;
    }

    addMessage("user", trimmed);
    activeAssistantId.current = null;

    const accepted = socketRef.current?.sendMessage(accessToken, trimmed, userId);
    if (!accepted) {
      addMessage("system", "Message could not be sent.");
    }

    setMessageText("");
  };

  const loadHistory = async () => {
    if (!session?.accessToken) {
      setStatusText("Invalid authenticated user");
      return;
    }

    setLoadingHistory(true);
    try {
      const response = await fetch(`${normalizeBaseUrl(apiBaseUrl)}/chat/history?limit=60`, {
        headers: {
          Authorization: `${session.tokenType} ${session.accessToken}`,
        },
      });
      if (!response.ok) {
        addMessage("system", "Could not fetch history from server.");
        return;
      }
      const data = (await response.json()) as Array<{ role: ChatMessage["role"]; content: string }>;
      const mapped: ChatMessage[] = data
        .map((item) => ({
          id: makeId(item.role),
          role: item.role,
          text: item.role === "user" ? (item.content || "") : sanitizeText(item.content || ""),
        }))
        .filter((m) => m.text.length > 0);
      setMessages(mapped);
    } catch (_error) {
      addMessage(
        "system",
        "Network request failed while loading history. If you are on a real phone, use API URL http://<your-lan-ip>:8000 (not 127.0.0.1) and run backend on 0.0.0.0.",
      );
    } finally {
      setLoadingHistory(false);
    }
  };

  const loadWorkout = async () => {
    if (!session?.userId) {
      setWorkoutError("Cannot load workout: missing user session.");
      return;
    }

    setWorkoutLoading(true);
    setWorkoutError(null);
    try {
      const response = await fetch(
        `${normalizeBaseUrl(apiBaseUrl)}/workouts/latest?user_id=${encodeURIComponent(String(session.userId))}`,
      );
      if (!response.ok) {
        if (response.status === 404) {
          setWorkoutData(null);
          setWorkoutError("No saved workout plan found yet for this account.");
          return;
        }
        setWorkoutError("Could not fetch workout plan from server.");
        return;
      }

      const payload = (await response.json()) as WorkoutResponseData;
      setWorkoutData(payload);
    } catch (_error) {
      setWorkoutError("Network request failed while fetching workout plan.");
    } finally {
      setWorkoutLoading(false);
    }
  };

  const openWorkoutScreen = () => {
    setActiveView("workout");
    if (!workoutData) {
      void loadWorkout();
    }
  };

  useEffect(() => {
    if (!session || connected) {
      return;
    }
    connectSocket()
  }, [session, connected, apiBaseUrl]);

  useEffect(() => {
    if (!session) {
      return;
    }
    void loadHistory();
  }, [session]);

  const scrollToBottom = () => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const submitAuth = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedPassword = password;

    if (!isLikelyEmail(normalizedEmail)) {
      setAuthError("Please provide a valid email address.");
      return;
    }

    if (normalizedPassword.length < 8) {
      setAuthError("Password must be at least 8 characters.");
      return;
    }

    if (utf8ByteLength(normalizedPassword) > 72) {
      setAuthError("Password is too long. Maximum supported size is 72 bytes.");
      return;
    }

    if (authMode === "signup" && normalizedPassword !== confirmPassword) {
      setAuthError("Password and confirm password do not match.");
      return;
    }

    setAuthLoading(true);
    setAuthError(null);

    try {
      const authResponse =
        authMode === "signup"
          ? await signupWithEmail(apiBaseUrl, normalizedEmail, normalizedPassword)
          : await loginWithEmail(apiBaseUrl, normalizedEmail, normalizedPassword);

      const nextSession: UserSession = {
        email: normalizedEmail,
        accessToken: authResponse.access_token,
        tokenType: authResponse.token_type,
        userId: authResponse.user_id,
      };

      setSession(nextSession);
      await persistSession(nextSession);
      setPassword("");
      setConfirmPassword("");
      setStatusText("Authenticated. Connect socket to chat.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Authentication failed";
      setAuthError(message);
    } finally {
      setAuthLoading(false);
    }
  };

  const logout = async () => {
    clearReconnectTimer();
    socketRef.current?.close();
    setConnected(false);
    setSession(null);
    setActiveView("chat");
    setMessages([]);
    setWorkoutData(null);
    setWorkoutError(null);
    setStatusText("Disconnected");
    setPassword("");
    setConfirmPassword("");
    setAuthError(null);
    await persistSession(null);
  };

  // Animated bouncing dots component
  const TypingDots = useMemo(
    () =>
      function Dots() {
        const dot1 = useRef(new Animated.Value(0)).current;
        const dot2 = useRef(new Animated.Value(0)).current;
        const dot3 = useRef(new Animated.Value(0)).current;

        useEffect(() => {
          const bounce = (dot: Animated.Value, delay: number) =>
            Animated.loop(
              Animated.sequence([
                Animated.delay(delay),
                Animated.timing(dot, { toValue: -6, duration: 280, useNativeDriver: true }),
                Animated.timing(dot, { toValue: 0, duration: 280, useNativeDriver: true }),
              ]),
            );
          const a1 = bounce(dot1, 0);
          const a2 = bounce(dot2, 160);
          const a3 = bounce(dot3, 320);
          a1.start();
          a2.start();
          a3.start();
          return () => {
            a1.stop();
            a2.stop();
            a3.stop();
          };
        }, [dot1, dot2, dot3]);

        return (
          <View style={styles.typingBubble}>
            <View style={styles.typingDotsRow}>
              {[dot1, dot2, dot3].map((dot, i) => (
                <Animated.View
                  key={i}
                  style={[styles.typingDot, { transform: [{ translateY: dot }] }]}
                />
              ))}
            </View>
          </View>
        );
      },
    [],
  );

  const statusColor = connected ? "#22C55E" : statusText.startsWith("Reconnecting") ? "#F59E0B" : "#EF4444";

  if (sessionLoading) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" backgroundColor="#0B0F1A" />
        <View style={styles.centeredPanel}>
          <Text style={styles.splashEmoji}>🏋️</Text>
          <ActivityIndicator color="#7C3AED" size="large" />
          <Text style={styles.subtitle}>Loading your session...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!session) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" backgroundColor="#0B0F1A" />
        <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={styles.authCard}>
            <Text style={styles.splashEmoji}>🏋️</Text>
            <Text style={styles.authTitle}>FitCoach AI</Text>
            <Text style={styles.authSubtitle}>Your AI-powered personal trainer</Text>

            <View style={styles.modeRow}>
              <Pressable
                style={[styles.modeButton, authMode === "login" && styles.modeButtonActive]}
                onPress={() => {
                  setAuthMode("login");
                  setAuthError(null);
                }}
              >
                <Text style={[styles.modeButtonText, authMode === "login" && styles.modeButtonTextActive]}>Login</Text>
              </Pressable>
              <Pressable
                style={[styles.modeButton, authMode === "signup" && styles.modeButtonActive]}
                onPress={() => {
                  setAuthMode("signup");
                  setAuthError(null);
                }}
              >
                <Text style={[styles.modeButtonText, authMode === "signup" && styles.modeButtonTextActive]}>Sign Up</Text>
              </Pressable>
            </View>

            <TextInput
              style={styles.input}
              placeholder="🌐 Server URL"
              placeholderTextColor="#6B7280"
              value={apiBaseUrl}
              onChangeText={setApiBaseUrl}
              autoCapitalize="none"
            />

            <TextInput
              style={styles.input}
              placeholder="📧 Email"
              placeholderTextColor="#6B7280"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
            />

            <TextInput
              style={styles.input}
              placeholder="🔒 Password"
              placeholderTextColor="#6B7280"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />

            {authMode === "signup" ? (
              <TextInput
                style={styles.input}
                placeholder="🔒 Confirm password"
                placeholderTextColor="#6B7280"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry
              />
            ) : null}

            {authError ? <Text style={styles.errorText}>⚠️ {authError}</Text> : null}

            <Pressable
              style={[styles.authButton, authLoading && styles.authButtonDisabled]}
              onPress={submitAuth}
              disabled={authLoading}
            >
              {authLoading ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.authButtonText}>
                  {authMode === "signup" ? "Create Account 🚀" : "Let's Go 💪"}
                </Text>
              )}
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  if (activeView === "workout") {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" backgroundColor="#0B0F1A" />
        <View style={styles.screen}>
          <View style={styles.workoutHeader}>
            <Pressable style={styles.backButton} onPress={() => setActiveView("chat")}>
              <Text style={styles.backButtonText}>← Chat</Text>
            </Pressable>
            <Text style={styles.headerTitle}>🏋️ My Plan</Text>
            <Pressable style={styles.refreshButton} onPress={loadWorkout}>
              <Text style={styles.refreshButtonText}>{workoutLoading ? "..." : "↻"}</Text>
            </Pressable>
          </View>

          <ScrollView style={styles.chatWrap} contentContainerStyle={styles.workoutContent}>
            {workoutLoading ? <ActivityIndicator style={styles.loader} color="#7C3AED" size="large" /> : null}
            {workoutError ? <Text style={styles.errorText}>⚠️ {workoutError}</Text> : null}

            {!workoutLoading && !workoutError && !workoutData?.plan ? (
              <View style={styles.emptyState}>
                <Text style={styles.emptyEmoji}>📋</Text>
                <Text style={styles.emptyTitle}>No Workout Plan Yet</Text>
                <Text style={styles.emptyHint}>Ask FitCoach to generate one for you!</Text>
              </View>
            ) : null}

            {workoutData?.plan ? (
              <View style={styles.workoutPlanCard}>
                <View style={styles.planHeader}>
                  <Text style={styles.planGoalLabel}>🎯 GOAL</Text>
                  <Text style={styles.planGoalValue}>{workoutData.plan.goal || "N/A"}</Text>
                </View>
                <View style={styles.planStatsRow}>
                  <View style={styles.planStat}>
                    <Text style={styles.planStatValue}>{workoutData.plan.days_per_week || "?"}</Text>
                    <Text style={styles.planStatLabel}>Days/Week</Text>
                  </View>
                  <View style={styles.planStat}>
                    <Text style={styles.planStatValue}>
                      {(workoutData.plan.weekly_plan || []).reduce((sum, d) => sum + (d.exercises?.length || 0), 0)}
                    </Text>
                    <Text style={styles.planStatLabel}>Exercises</Text>
                  </View>
                </View>
                {workoutData.plan.notes ? <Text style={styles.planNotes}>💡 {workoutData.plan.notes}</Text> : null}
              </View>
            ) : null}

            {(workoutData?.plan?.weekly_plan || []).map((day, dayIndex) => (
              <View key={`${day.title || "day"}-${dayIndex}`} style={styles.dayCard}>
                <View style={styles.dayHeader}>
                  <Text style={styles.dayNumber}>Day {dayIndex + 1}</Text>
                  <Text style={styles.dayTitle}>{day.title || `Day ${dayIndex + 1}`}</Text>
                </View>
                <Text style={styles.dayFocus}>{day.focus || "General"}</Text>

                {(day.exercises || []).map((exercise, exIndex) => (
                  <View key={`${exercise.name || "exercise"}-${exIndex}`} style={styles.exerciseCard}>
                    <View style={styles.exerciseTop}>
                      <View style={styles.exerciseIndex}>
                        <Text style={styles.exerciseIndexText}>{exIndex + 1}</Text>
                      </View>
                      <View style={styles.exerciseInfo}>
                        <Text style={styles.exerciseName}>{exercise.name || "Exercise"}</Text>
                        <Text style={styles.exerciseMeta}>
                          {exercise.sets || "?"} sets × {exercise.reps || "?"} reps
                        </Text>
                      </View>
                    </View>
                    {(() => {
                      const preview = toYouTubeVideo(exercise.video_url, exercise.name || "Exercise");
                      return preview ? <YouTubeShort video={preview} /> : null;
                    })()}
                  </View>
                ))}
              </View>
            ))}
          </ScrollView>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor="#0B0F1A" />
      <KeyboardAvoidingView
        style={styles.screen}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 10 : 0}
      >
        {/* Header */}
        <View style={styles.chatHeader}>
          <View style={styles.headerLeft}>
            <Text style={styles.headerLogo}>🏋️</Text>
            <View>
              <Text style={styles.headerTitle}>FitCoach AI</Text>
              <View style={styles.statusRow}>
                <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
                <Text style={[styles.statusText, { color: statusColor }]}>{statusText}</Text>
              </View>
            </View>
          </View>
          <View style={styles.headerActions}>
            <Pressable style={styles.workoutButton} onPress={openWorkoutScreen}>
              <Text style={styles.workoutButtonText}>📋 Plan</Text>
            </Pressable>
            <Pressable style={styles.logoutButton} onPress={logout}>
              <Text style={styles.logoutButtonText}>↩</Text>
            </Pressable>
          </View>
        </View>

        {/* Messages */}
        <View style={styles.chatWrap}>
          <ScrollView
            ref={scrollRef}
            style={styles.chatScroll}
            contentContainerStyle={styles.chatContent}
            onContentSizeChange={scrollToBottom}
          >
            {!messages.length ? (
              <View style={styles.emptyState}>
                <Text style={styles.emptyEmoji}>💬</Text>
                <Text style={styles.emptyTitle}>Start a Conversation</Text>
                <Text style={styles.emptyHint}>Ask for a workout plan, exercise tips, or anything fitness related!</Text>
              </View>
            ) : null}
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {showTypingDots ? <TypingDots /> : null}
          </ScrollView>
        </View>

        {/* Composer */}
        <View style={styles.composer}>
          <TextInput
            style={[styles.composerInput, styles.flexOne]}
            placeholder="Ask me anything about fitness..."
            placeholderTextColor="#6B7280"
            value={messageText}
            onChangeText={setMessageText}
            multiline
          />
          <Pressable style={styles.sendButton} onPress={sendMessage}>
            <Text style={styles.sendButtonIcon}>↑</Text>
          </Pressable>
        </View>

        {loadingHistory ? <ActivityIndicator style={styles.loader} color="#7C3AED" /> : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#0B0F1A",
  },
  centeredPanel: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    gap: 12,
  },
  screen: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 12,
  },

  // ──── Auth ─────────────────────────────────────
  authCard: {
    marginTop: 60,
    borderWidth: 1,
    borderColor: "#1E1B4B",
    borderRadius: 24,
    padding: 24,
    backgroundColor: "#111827",
    gap: 14,
    shadowColor: "#7C3AED",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 6,
  },
  splashEmoji: {
    fontSize: 48,
    textAlign: "center",
  },
  authTitle: {
    color: "#F9FAFB",
    fontSize: 28,
    fontWeight: "900",
    textAlign: "center",
    letterSpacing: -0.5,
  },
  authSubtitle: {
    color: "#9CA3AF",
    fontSize: 15,
    textAlign: "center",
    marginBottom: 8,
  },
  modeRow: {
    flexDirection: "row",
    gap: 8,
    backgroundColor: "#1F2937",
    borderRadius: 14,
    padding: 4,
  },
  modeButton: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    borderRadius: 10,
    paddingVertical: 10,
  },
  modeButtonActive: {
    backgroundColor: "#7C3AED",
  },
  modeButtonText: {
    color: "#9CA3AF",
    fontWeight: "700",
    fontSize: 15,
  },
  modeButtonTextActive: {
    color: "#FFFFFF",
  },
  input: {
    borderWidth: 1,
    borderColor: "#374151",
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
    color: "#F9FAFB",
    backgroundColor: "#1F2937",
    fontSize: 16,
    maxHeight: 120,
  },
  authButton: {
    justifyContent: "center",
    alignItems: "center",
    borderRadius: 14,
    backgroundColor: "#7C3AED",
    paddingVertical: 16,
    marginTop: 4,
  },
  authButtonDisabled: {
    opacity: 0.6,
  },
  authButtonText: {
    color: "#FFFFFF",
    fontWeight: "800",
    fontSize: 17,
  },

  // ──── Chat header ──────────────────────────────
  chatHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 8,
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  headerLogo: {
    fontSize: 28,
  },
  headerTitle: {
    color: "#F9FAFB",
    fontSize: 20,
    fontWeight: "800",
    letterSpacing: -0.3,
  },
  headerActions: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    marginTop: 1,
  },
  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  statusText: {
    fontSize: 11,
    fontWeight: "600",
  },
  subtitle: {
    color: "#9CA3AF",
    fontSize: 14,
  },

  // ──── Buttons ──────────────────────────────────
  workoutButton: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: 12,
    backgroundColor: "#1F2937",
    borderWidth: 1,
    borderColor: "#374151",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  workoutButtonText: {
    color: "#E5E7EB",
    fontWeight: "700",
    fontSize: 13,
  },
  logoutButton: {
    borderRadius: 12,
    backgroundColor: "#1F2937",
    borderWidth: 1,
    borderColor: "#374151",
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  logoutButtonText: {
    color: "#EF4444",
    fontWeight: "800",
    fontSize: 16,
  },
  sendButton: {
    justifyContent: "center",
    alignItems: "center",
    borderRadius: 22,
    backgroundColor: "#7C3AED",
    width: 44,
    height: 44,
  },
  sendButtonIcon: {
    color: "#FFFFFF",
    fontWeight: "900",
    fontSize: 20,
  },
  backButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    backgroundColor: "#1F2937",
    borderWidth: 1,
    borderColor: "#374151",
  },
  backButtonText: {
    color: "#E5E7EB",
    fontWeight: "700",
    fontSize: 14,
  },
  refreshButton: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    backgroundColor: "#1F2937",
    borderWidth: 1,
    borderColor: "#374151",
  },
  refreshButtonText: {
    color: "#E5E7EB",
    fontWeight: "800",
    fontSize: 18,
  },
  flexOne: {
    flex: 1,
  },

  // ──── Chat area ────────────────────────────────
  chatWrap: {
    flex: 1,
    marginTop: 8,
    borderWidth: 1,
    borderColor: "#1E1B4B",
    borderRadius: 20,
    backgroundColor: "#111827",
    overflow: "hidden",
  },
  chatScroll: {
    flex: 1,
  },
  chatContent: {
    padding: 14,
  },
  emptyState: {
    alignItems: "center",
    marginVertical: 40,
    gap: 8,
  },
  emptyEmoji: {
    fontSize: 42,
  },
  emptyTitle: {
    color: "#E5E7EB",
    fontWeight: "700",
    fontSize: 18,
  },
  emptyHint: {
    color: "#6B7280",
    fontSize: 14,
    textAlign: "center",
    paddingHorizontal: 24,
  },
  typingBubble: {
    alignSelf: "flex-start",
    backgroundColor: "#1F2937",
    borderRadius: 18,
    borderTopLeftRadius: 4,
    paddingVertical: 14,
    paddingHorizontal: 20,
    marginVertical: 6,
    borderWidth: 1,
    borderColor: "#374151",
  },
  typingDotsRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  typingDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#7C3AED",
  },
  composer: {
    flexDirection: "row",
    gap: 10,
    marginTop: 10,
    marginBottom: 4,
    alignItems: "flex-end",
  },
  composerInput: {
    borderWidth: 1,
    borderColor: "#374151",
    borderRadius: 22,
    paddingHorizontal: 18,
    paddingVertical: 12,
    color: "#F9FAFB",
    backgroundColor: "#1F2937",
    fontSize: 15,
    maxHeight: 120,
  },

  // ──── Workout plan ─────────────────────────────
  workoutHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
  },
  workoutContent: {
    padding: 14,
    paddingBottom: 32,
  },
  workoutPlanCard: {
    borderWidth: 1,
    borderColor: "#1E1B4B",
    borderRadius: 18,
    padding: 18,
    backgroundColor: "#111827",
    marginBottom: 16,
    gap: 12,
  },
  planHeader: {
    gap: 4,
  },
  planGoalLabel: {
    color: "#7C3AED",
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 1.5,
  },
  planGoalValue: {
    color: "#F9FAFB",
    fontSize: 20,
    fontWeight: "800",
  },
  planStatsRow: {
    flexDirection: "row",
    gap: 16,
  },
  planStat: {
    flex: 1,
    backgroundColor: "#1F2937",
    borderRadius: 12,
    padding: 12,
    alignItems: "center",
  },
  planStatValue: {
    color: "#F9FAFB",
    fontSize: 22,
    fontWeight: "900",
  },
  planStatLabel: {
    color: "#9CA3AF",
    fontSize: 12,
    fontWeight: "600",
    marginTop: 2,
  },
  planNotes: {
    color: "#D1D5DB",
    fontSize: 13,
    lineHeight: 19,
    fontStyle: "italic",
  },
  dayCard: {
    borderWidth: 1,
    borderColor: "#1E293B",
    borderRadius: 18,
    padding: 16,
    backgroundColor: "#0F172A",
    marginBottom: 14,
  },
  dayHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 2,
  },
  dayNumber: {
    color: "#7C3AED",
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 1,
    backgroundColor: "#7C3AED22",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    overflow: "hidden",
  },
  dayTitle: {
    color: "#F9FAFB",
    fontSize: 17,
    fontWeight: "700",
    flex: 1,
    flexShrink: 1,
  },
  dayFocus: {
    color: "#9CA3AF",
    fontSize: 13,
    marginBottom: 12,
  },
  exerciseCard: {
    borderWidth: 1,
    borderColor: "#1E293B",
    borderRadius: 14,
    padding: 12,
    marginBottom: 10,
    backgroundColor: "#111827",
    gap: 8,
  },
  exerciseTop: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  exerciseIndex: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#7C3AED",
    justifyContent: "center",
    alignItems: "center",
  },
  exerciseIndexText: {
    color: "#FFFFFF",
    fontWeight: "800",
    fontSize: 13,
  },
  exerciseInfo: {
    flex: 1,
    gap: 2,
  },
  exerciseName: {
    color: "#F9FAFB",
    fontSize: 15,
    fontWeight: "700",
  },
  exerciseMeta: {
    color: "#9CA3AF",
    fontSize: 13,
    fontWeight: "500",
  },

  // ──── Misc ─────────────────────────────────────
  errorText: {
    color: "#FCA5A5",
    fontSize: 13,
    textAlign: "center",
  },
  loader: {
    marginTop: 12,
  },
});
