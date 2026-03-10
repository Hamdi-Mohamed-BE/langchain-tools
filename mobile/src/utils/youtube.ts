import ENV from "../config/env";

const YOUTUBE_API_KEY = ENV.YOUTUBE_API_KEY;

export interface YouTubeVideo {
  id: string;
  title: string;
  thumbnail: string;
}

function extractYouTubeVideoId(url: string): string | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    const pathParts = parsed.pathname.split("/").filter(Boolean);

    if (host === "youtu.be" && pathParts[0]) {
      return pathParts[0];
    }

    if (host.includes("youtube.com") && parsed.pathname === "/watch") {
      return parsed.searchParams.get("v");
    }

    if (host.includes("youtube.com") && pathParts[0] === "shorts" && pathParts[1]) {
      return pathParts[1];
    }

    if (host.includes("youtube.com") && pathParts[0] === "embed" && pathParts[1]) {
      return pathParts[1];
    }
  } catch (_error) {
    return null;
  }

  return null;
}

export function toYouTubeVideo(videoUrl: string | null | undefined, title: string): YouTubeVideo | null {
  if (!videoUrl) {
    return null;
  }

  const id = extractYouTubeVideoId(videoUrl);
  if (!id) {
    return null;
  }

  return {
    id,
    title,
    thumbnail: `https://i.ytimg.com/vi/${id}/mqdefault.jpg`,
  };
}

export const searchYouTubeShorts = async (
  agentName: string,
  mapName: string,
  pageToken?: string,
): Promise<{
  videos: YouTubeVideo[];
  nextPageToken?: string;
}> => {
  if (!YOUTUBE_API_KEY) {
    return { videos: [] };
  }

  try {
    const url =
      "https://youtube.googleapis.com/youtube/v3/search?" +
      "part=snippet&" +
      `q=${encodeURIComponent(`${agentName} ${mapName} valorant tips shorts`)}&` +
      "type=video&" +
      "maxResults=30&" +
      `key=${YOUTUBE_API_KEY}` +
      (pageToken ? `&pageToken=${pageToken}` : "");

    const response = await fetch(url);
    const data = (await response.json()) as {
      items?: Array<{
        id?: { videoId?: string };
        snippet?: { title?: string; thumbnails?: { medium?: { url?: string } } };
      }>;
      nextPageToken?: string;
      error?: { message?: string };
    };

    if (!response.ok) {
      console.error("YouTube API Error:", data.error?.message || data);
      return { videos: [] };
    }

    const videos = (data.items || [])
      .map((item) => ({
        id: item.id?.videoId || "",
        title: item.snippet?.title || "Untitled",
        thumbnail: item.snippet?.thumbnails?.medium?.url || "",
      }))
      .filter((item) => item.id && item.thumbnail);

    return {
      videos,
      nextPageToken: data.nextPageToken,
    };
  } catch (error) {
    console.error("Error fetching YouTube shorts:", error);
    return { videos: [] };
  }
};
