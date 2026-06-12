import { createClient } from "@supabase/supabase-js";
import { Challenge, challengeFor } from "./demoData";

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://placeholder.supabase.co",
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "placeholder"
);

// ── Types ──

export interface Checkin {
  date: string;
  makeup: boolean;
  completed_at?: string;
}

export interface Recording {
  id: string;
  date: string;
  sentence_idx: number;
  storage_path: string;
  duration_sec: number | null;
  created_at: string;
  signedUrl?: string | null;
}

export interface Tweak {
  id: string;
  date: string;
  sentence_idx: number;
  start_sec: number;
  end_sec: number;
}

// ── Daily Challenge ──

export async function getChallengeForDate(date: string): Promise<Challenge> {
  try {
    const { data, error } = await supabase
      .from("daily_challenges")
      .select("*")
      .eq("date", date)
      .single();

    if (error || !data) return challengeFor(date);

    return {
      video: {
        youtube_id: data.video_id,
        title: data.video_title,
        channel: data.video_channel,
      },
      sentences: data.sentences,
    };
  } catch {
    return challengeFor(date);
  }
}

// ── Checkins ──

export async function getCheckins(): Promise<Checkin[]> {
  try {
    const { data, error } = await supabase
      .from("checkins")
      .select("*")
      .order("date", { ascending: false });
    if (error) throw error;
    return data || [];
  } catch (e) {
    console.error("getCheckins error:", e);
    return [];
  }
}

export async function putCheckin(
  date: string,
  makeup: boolean
): Promise<void> {
  const { error } = await supabase
    .from("checkins")
    .upsert({ date, makeup, completed_at: new Date().toISOString() });
  if (error) throw error;
}

// ── Recordings ──

export async function deleteRecording(id: string, storagePath: string): Promise<void> {
  const { error: storageError } = await supabase.storage
    .from("recordings")
    .remove([storagePath]);
  if (storageError) throw storageError;
  const { error: dbError } = await supabase.from("recordings").delete().eq("id", id);
  if (dbError) throw dbError;
}

export async function addRecording(
  date: string,
  sentenceIdx: number,
  blob: Blob
): Promise<Recording> {
  const timestamp = Date.now();
  const ext = blob.type.includes("mp4") ? "m4a"
    : blob.type.includes("ogg") ? "ogg"
    : "webm";
  const storagePath = `${date}/${sentenceIdx}/${timestamp}.${ext}`;

  const { error: uploadError } = await supabase.storage
    .from("recordings")
    .upload(storagePath, blob, { contentType: blob.type || "audio/webm" });

  if (uploadError) throw uploadError;

  const durationSec = await getAudioDuration(blob).catch(() => null);

  const { data, error: insertError } = await supabase
    .from("recordings")
    .insert({
      date,
      sentence_idx: sentenceIdx,
      storage_path: storagePath,
      duration_sec: durationSec,
    })
    .select()
    .single();

  if (insertError) throw insertError;
  return data;
}

export async function getRecordingsForDate(
  date: string
): Promise<Recording[]> {
  try {
    const { data, error } = await supabase
      .from("recordings")
      .select("*")
      .eq("date", date)
      .order("created_at", { ascending: true });

    if (error) throw error;
    if (!data || data.length === 0) return [];

    const withUrls = await Promise.all(
      data.map(async (rec: Recording) => {
        const { data: signedData } = await supabase.storage
          .from("recordings")
          .createSignedUrl(rec.storage_path, 60 * 60 * 24 * 7); // 7 days
        return { ...rec, signedUrl: signedData?.signedUrl ?? null };
      })
    );

    return withUrls;
  } catch (e) {
    console.error("getRecordingsForDate error:", e);
    return [];
  }
}

// ── Tweaks ──

export async function putTweak(
  date: string,
  sentenceIdx: number,
  startSec: number,
  endSec: number
): Promise<void> {
  const id = `${date}|${sentenceIdx}`;
  const { error } = await supabase.from("tweaks").upsert({
    id,
    date,
    sentence_idx: sentenceIdx,
    start_sec: startSec,
    end_sec: endSec,
    updated_at: new Date().toISOString(),
  });
  if (error) throw error;
}

export async function getTweaksForDate(date: string): Promise<Tweak[]> {
  try {
    const { data, error } = await supabase
      .from("tweaks")
      .select("*")
      .eq("date", date);
    if (error) throw error;
    return data || [];
  } catch (e) {
    console.error("getTweaksForDate error:", e);
    return [];
  }
}

// ── Helpers ──

function getAudioDuration(blob: Blob): Promise<number> {
  return new Promise((resolve, reject) => {
    const audio = new Audio();
    audio.src = URL.createObjectURL(blob);
    audio.onloadedmetadata = () => {
      URL.revokeObjectURL(audio.src);
      resolve(audio.duration);
    };
    audio.onerror = reject;
  });
}
