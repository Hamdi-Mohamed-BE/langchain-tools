import { useState } from "react";
import { Dimensions, StyleSheet, Text, View } from "react-native";
import YoutubePlayer from "react-native-youtube-iframe";
import { FontAwesome } from "@expo/vector-icons";

import type { YouTubeVideo } from "../utils/youtube";

const { width } = Dimensions.get("window");
const videoHeight = (width - 72) * (9 / 16);

interface Props {
  video: YouTubeVideo;
}

export default function YouTubeShort({ video }: Props) {
  const [playing, setPlaying] = useState(false);

  return (
    <View style={styles.container}>
      <YoutubePlayer
        height={videoHeight}
        width={width - 72}
        videoId={video.id}
        play={playing}
        onChangeState={(state: string) => {
          if (state === "ended") {
            setPlaying(false);
          }
        }}
        initialPlayerParams={{
          controls: true,
          modestbranding: true,
          rel: false,
        }}
        webViewProps={{
          renderToHardwareTextureAndroid: true,
        }}
      />
      <View style={styles.infoContainer}>
        <View style={styles.titleContainer}>
          <FontAwesome name="youtube-play" size={22} color="#FF4655" />
          <Text style={styles.title} numberOfLines={2}>
            {video.title}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: "100%",
    marginTop: 8,
    marginBottom: 4,
    backgroundColor: "#0F172A",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#1E293B",
    overflow: "hidden",
  },
  infoContainer: {
    padding: 10,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#111827",
  },
  titleContainer: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  title: {
    flex: 1,
    color: "#E5E7EB",
    fontSize: 13,
    fontWeight: "600",
  },
});
