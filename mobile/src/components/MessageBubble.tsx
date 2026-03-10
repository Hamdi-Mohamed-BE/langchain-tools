import React from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { ChatMessage } from "../types/chat";
import { toYouTubeVideo } from "../utils/youtube";
import YouTubeShort from "./YouTubeShort";

type MessageBubbleProps = {
  message: ChatMessage;
};

const ROLE_CONFIG = {
  user: { emoji: "🧑", label: "You", bg: "#1E3A5F", border: "#3B82F6", labelColor: "#93C5FD", align: "flex-end" as const },
  assistant: { emoji: "🤖", label: "FitCoach", bg: "#1E1B4B", border: "#7C3AED", labelColor: "#C4B5FD", align: "flex-start" as const },
  system: { emoji: "⚙️", label: "System", bg: "#1C1917", border: "#F59E0B", labelColor: "#FDE68A", align: "center" as const },
  tool: { emoji: "🔧", label: "Tool", bg: "#0C1E0C", border: "#22C55E", labelColor: "#86EFAC", align: "flex-start" as const },
} as const;

const URL_REGEX = /https?:\/\/[^\s)\]>]+/gi;
const YOUTUBE_HOST_REGEX = /youtube\.com|youtu\.be/i;

/** Extract all YouTube URLs from text. */
function extractYouTubeUrls(text: string): string[] {
  const matches = text.match(URL_REGEX) || [];
  return matches.filter((url) => YOUTUBE_HOST_REGEX.test(url));
}

/** Parse a markdown-ish string into styled React Native nodes, with embedded YouTube players. */
function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];

  // Collect YouTube URLs to embed at the end (avoid duplicating inline)
  const youtubeUrls = extractYouTubeUrls(text);
  const embeddedSet = new Set(youtubeUrls);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";

    // Headings: ### / ## / #
    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = (headingMatch[1] ?? "#").length;
      const size = level === 1 ? 20 : level === 2 ? 18 : 16;
      nodes.push(
        <Text key={i} style={[styles.body, { fontWeight: "800", fontSize: size, marginTop: 8, marginBottom: 4 }]}>
          {renderInline(headingMatch[2] ?? "", embeddedSet)}
        </Text>,
      );
      continue;
    }

    // Bullet list items: * or -
    const bulletMatch = line.match(/^\s*[*\-]\s+(.+)$/);
    if (bulletMatch) {
      nodes.push(
        <View key={i} style={styles.listItem}>
          <Text style={styles.bullet}>•</Text>
          <Text style={[styles.body, styles.listText]}>{renderInline(bulletMatch[1] ?? "", embeddedSet)}</Text>
        </View>,
      );
      continue;
    }

    // Empty line → small spacer
    if (!line.trim()) {
      nodes.push(<View key={i} style={{ height: 6 }} />);
      continue;
    }

    // Normal paragraph
    nodes.push(
      <Text key={i} style={styles.body}>
        {renderInline(line, embeddedSet)}
      </Text>,
    );
  }

  // Append embedded YouTube players for all YouTube URLs found in the message
  youtubeUrls.forEach((url, idx) => {
    const video = toYouTubeVideo(url, "Exercise Video");
    if (video) {
      nodes.push(
        <View key={`yt-${idx}`} style={{ marginTop: 8 }}>
          <YouTubeShort video={video} />
        </View>,
      );
    }
  });

  return nodes;
}

/** Render inline markdown: **bold**, *italic*, and clickable URLs */
function renderInline(text: string, youtubeEmbedded?: Set<string>): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // Combined regex: URLs, **bold**, *italic*
  const regex = /(https?:\/\/[^\s)\]>]+|\*\*(.+?)\*\*|\*(.+?)\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let idx = 0;

  while ((match = regex.exec(text)) !== null) {
    // Push preceding plain text
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }

    const full = match[0];

    if (full.startsWith("http")) {
      // URL — if it's a YouTube URL that will be embedded, just show label
      const isYouTube = youtubeEmbedded?.has(full);
      parts.push(
        <Text
          key={`u${idx}`}
          style={styles.link}
          onPress={() => Linking.openURL(full)}
        >
          {isYouTube ? "▶ Watch Video" : full}
        </Text>,
      );
    } else if (match[2] != null) {
      // **bold**
      parts.push(
        <Text key={`b${idx}`} style={{ fontWeight: "700" }}>
          {match[2]}
        </Text>,
      );
    } else if (match[3] != null) {
      // *italic*
      parts.push(
        <Text key={`i${idx}`} style={{ fontStyle: "italic" }}>
          {match[3]}
        </Text>,
      );
    }
    last = match.index + full.length;
    idx++;
  }

  if (last < text.length) {
    parts.push(text.slice(last));
  }

  return parts.length > 0 ? parts : [text];
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const config = ROLE_CONFIG[message.role] ?? ROLE_CONFIG.system;
  const isUser = message.role === "user";

  return (
    <View style={[styles.row, { justifyContent: config.align }]}>
      {!isUser && (
        <View style={[styles.avatar, { backgroundColor: config.border + "22", borderColor: config.border }]}>
          <Text style={styles.avatarEmoji}>{config.emoji}</Text>
        </View>
      )}
      <View
        style={[
          styles.bubble,
          {
            backgroundColor: config.bg,
            borderColor: config.border,
            borderTopLeftRadius: isUser ? 20 : 4,
            borderTopRightRadius: isUser ? 4 : 20,
            maxWidth: "80%",
          },
        ]}
      >
        <Text style={[styles.roleLabel, { color: config.labelColor }]}>{config.label}</Text>
        {isUser ? (
          <Text style={styles.body} selectable>
            {message.text}
          </Text>
        ) : (
          <View style={styles.markdownWrap}>{renderMarkdown(message.text)}</View>
        )}
      </View>
      {isUser && (
        <View style={[styles.avatar, { backgroundColor: config.border + "22", borderColor: config.border }]}>
          <Text style={styles.avatarEmoji}>{config.emoji}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "flex-end",
    marginBottom: 14,
    gap: 8,
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    borderWidth: 1.5,
    justifyContent: "center",
    alignItems: "center",
  },
  avatarEmoji: {
    fontSize: 16,
  },
  bubble: {
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderWidth: 1,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 3,
  },
  roleLabel: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.2,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  markdownWrap: {
    gap: 2,
  },
  body: {
    color: "#F1F5F9",
    lineHeight: 22,
    fontSize: 15,
  },
  listItem: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
    paddingLeft: 4,
  },
  bullet: {
    color: "#7C3AED",
    fontSize: 15,
    lineHeight: 22,
    fontWeight: "700",
  },
  listText: {
    flex: 1,
  },
  link: {
    color: "#818CF8",
    textDecorationLine: "underline",
    fontSize: 15,
    lineHeight: 22,
  },
});
