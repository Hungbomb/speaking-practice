"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import SentenceCard from "./SentenceCard";
import { Challenge, Sentence } from "@/lib/demoData";
import {
  getChallengeForDate,
  getTweaksForDate,
  getRecordingsForDate,
  putCheckin,
  Recording,
} from "@/lib/supabase";

declare global {
  interface Window {
    YT: {
      Player: new (
        el: string | HTMLElement,
        opts: {
          videoId: string;
          playerVars?: Record<string, unknown>;
          events?: {
            onReady?: () => void;
            onError?: (e: { data: number }) => void;
            onStateChange?: (e: { data: number }) => void;
          };
        }
      ) => YTPlayer;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

interface YTPlayer {
  seekTo: (t: number, allowSeekAhead: boolean) => void;
  playVideo: () => void;
  pauseVideo: () => void;
  getCurrentTime: () => number;
  getPlayerState: () => number;
  cueVideoById: (opts: { videoId: string; startSeconds: number }) => void;
  destroy: () => void;
}

interface Props {
  date: string;
  checkinMap: Map<string, { makeup: boolean }>;
  today: string;
  onCheckin: (date: string, makeup: boolean) => void;
  onLoadDate: (date: string) => void;
  onToast: (msg: string) => void;
}

const PAD = 1.5;
const fmt = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(
    Math.floor(s % 60)
  ).padStart(2, "0")}.${Math.floor((s * 10) % 10)}`;

const z2 = (n: number) => String(n).padStart(2, "0");

function zhDate(dateISO: string) {
  const [y, m, d] = dateISO.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${dt.getMonth() + 1} 月 ${dt.getDate()} 日`;
}

export default function PracticeView({
  date,
  checkinMap,
  today,
  onCheckin,
  onLoadDate,
  onToast,
}: Props) {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [winStart, setWinStart] = useState(0);
  const [winEnd, setWinEnd] = useState(1);
  const [loopSeg, setLoopSeg] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playheadPct, setPlayheadPct] = useState<number | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [recordedSet, setRecordedSet] = useState<Set<number>>(new Set());
  const [ytReady, setYtReady] = useState(false);
  const [ytError, setYtError] = useState<string | null>(null);

  const playerRef = useRef<YTPlayer | null>(null);
  const pendingVideoRef = useRef<{ id: string; t: number } | null>(null);
  const loopSegRef = useRef<number | null>(null);
  const sentencesRef = useRef<Sentence[]>([]);
  const winStartRef = useRef(0);
  const winEndRef = useRef(1);
  const ytReadyRef = useRef(false);

  loopSegRef.current = loopSeg;
  sentencesRef.current = sentences;
  winStartRef.current = winStart;
  winEndRef.current = winEnd;
  ytReadyRef.current = ytReady;

  // Load challenge data
  useEffect(() => {
    let cancelled = false;
    async function load() {
      const ch = await getChallengeForDate(date);
      if (cancelled) return;

      const tweaks = await getTweaksForDate(date);
      const sents: Sentence[] = JSON.parse(JSON.stringify(ch.sentences));
      for (const tw of tweaks) {
        if (sents[tw.sentence_idx]) {
          sents[tw.sentence_idx].start = tw.start_sec;
          sents[tw.sentence_idx].end = tw.end_sec;
        }
      }

      const starts = sents.map((s) => s.start);
      const ends = sents.map((s) => s.end);
      const ws = Math.max(0, Math.min(...starts) - PAD);
      const we = Math.max(...ends) + PAD;

      setChallenge(ch);
      setSentences(sents);
      setWinStart(ws);
      setWinEnd(we);
      setLoopSeg(null);
      setRecordedSet(new Set());

      if (ytReadyRef.current && playerRef.current) {
        playerRef.current.cueVideoById({
          videoId: ch.video.youtube_id,
          startSeconds: Math.floor(ws),
        });
      } else {
        pendingVideoRef.current = {
          id: ch.video.youtube_id,
          t: Math.floor(ws),
        };
      }

      const recs = await getRecordingsForDate(date);
      if (!cancelled) {
        setRecordings(recs);
        const seen = new Set(recs.map((r) => r.sentence_idx));
        setRecordedSet(seen);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [date]);

  // Mount YouTube IFrame API once
  useEffect(() => {
    const existing = document.querySelector(
      'script[src="https://www.youtube.com/iframe_api"]'
    );

    window.onYouTubeIframeAPIReady = () => {
      const p = new window.YT.Player("yt-player", {
        videoId: "",
        playerVars: { rel: 0, playsinline: 1, origin: location.origin },
        events: {
          onReady() {
            setYtReady(true);
            ytReadyRef.current = true;
            if (pendingVideoRef.current) {
              p.cueVideoById({
                videoId: pendingVideoRef.current.id,
                startSeconds: pendingVideoRef.current.t,
              });
              pendingVideoRef.current = null;
            }
          },
          onError(e) {
            setYtError(`YouTube 載入失敗（錯誤碼 ${e.data}）`);
          },
          onStateChange(e) {
            setIsPlaying(e.data === 1);
          },
        },
      });
      playerRef.current = p;
    };

    if (!existing) {
      const tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(tag);
    } else if (window.YT?.Player) {
      window.onYouTubeIframeAPIReady();
    }

    return () => {
      window.onYouTubeIframeAPIReady = undefined;
    };
  }, []);

  // Polling loop: loop segment + playhead
  useEffect(() => {
    const id = setInterval(() => {
      const p = playerRef.current;
      if (!p || !ytReadyRef.current || !p.getCurrentTime) return;
      const t = p.getCurrentTime();
      const playing = p.getPlayerState() === 1;
      setIsPlaying(playing);

      const seg = loopSegRef.current;
      if (seg !== null && playing) {
        const s = sentencesRef.current[seg];
        if (s && (t > s.end || t < s.start - 1)) {
          p.seekTo(s.start, true);
        }
      }

      const ws = winStartRef.current;
      const we = winEndRef.current;
      if (t >= ws && t <= we && playing) {
        setPlayheadPct(((t - ws) / (we - ws)) * 100);
      } else {
        setPlayheadPct(null);
      }
    }, 120);
    return () => clearInterval(id);
  }, []);

  const handleLoopToggle = useCallback(
    (i: number) => {
      const next = loopSeg === i ? null : i;
      setLoopSeg(next);
      if (next === null) {
        playerRef.current?.pauseVideo();
        return;
      }
      if (!ytReadyRef.current) {
        onToast("播放器尚未就緒");
        return;
      }
      const s = sentencesRef.current[next];
      if (s) {
        playerRef.current?.seekTo(s.start, true);
        playerRef.current?.playVideo();
      }
    },
    [loopSeg, onToast]
  );

  const handlePauseToggle = useCallback(() => {
    if (!ytReadyRef.current) { onToast("播放器尚未就緒"); return; }
    const state = playerRef.current?.getPlayerState();
    if (state === 1) playerRef.current?.pauseVideo();
    else playerRef.current?.playVideo();
  }, [onToast]);

  const handleTimeAdjust = useCallback(
    (idx: number, field: "start" | "end", delta: number) => {
      setSentences((prev) => {
        const next = [...prev];
        const s = { ...next[idx] };
        if (field === "start") s.start = Math.max(0, +(s.start + delta).toFixed(1));
        else s.end = +(s.end + delta).toFixed(1);
        next[idx] = s;
        const starts = next.map((x) => x.start);
        const ends = next.map((x) => x.end);
        const ws = Math.max(0, Math.min(...starts) - PAD);
        const we = Math.max(...ends) + PAD;
        setWinStart(ws);
        setWinEnd(we);
        return next;
      });
    },
    []
  );

  const handleRecordingAdded = useCallback(
    (rec: Recording, blobUrl: string) => {
      const withUrl = { ...rec, signedUrl: blobUrl };
      setRecordings((prev) => [...prev, withUrl]);
      setRecordedSet((prev) => {
        const next = new Set(prev);
        next.add(rec.sentence_idx);
        return next;
      });
    },
    []
  );

  const handleCheckin = useCallback(async () => {
    const makeup = date !== today;
    try {
      await putCheckin(date, makeup);
      onCheckin(date, makeup);
      onToast(makeup ? `已完成 ${zhDate(date)} 的補挑戰 ✦` : "已完成今日打卡 ✦");
    } catch {
      onToast("打卡失敗，請稍後再試");
    }
  }, [date, today, onCheckin, onToast]);

  const isToday = date === today;
  const checkinRec = checkinMap.get(date);
  const needCount = sentences.length;
  const doneCount = recordedSet.size;
  const canCheckin = needCount > 0 && doneCount >= needCount && !checkinRec;

  return (
    <div>
      {/* Mode bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          flexWrap: "wrap",
          background: "var(--peach)",
          borderRadius: 20,
          padding: "13px 20px",
          marginBottom: 14,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>
            {isToday
              ? `今日挑戰 · ${zhDate(date)}`
              : checkinRec
              ? `回顧 · `
              : `補挑戰 · `}
            {!isToday && (
              <em style={{ fontStyle: "normal", color: "var(--orange)" }}>
                {zhDate(date)}
              </em>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>
            {isToday
              ? "完成 3 句錄音後打卡"
              : checkinRec
              ? "重聽當天的錄音，也可以再多錄幾個 take"
              : "完成當天的 3 句錄音後，才能補打卡"}
          </div>
        </div>
        {!isToday && (
          <button
            onClick={() => onLoadDate(today)}
            style={{
              border: "none",
              background: "var(--card)",
              borderRadius: 999,
              padding: "7px 16px",
              fontSize: 12.5,
              fontFamily: "inherit",
              cursor: "pointer",
              color: "var(--ink)",
              fontWeight: 500,
            }}
          >
            ↩ 回到今日
          </button>
        )}
      </div>

      {/* Video card */}
      {challenge && (
        <div
          style={{
            background: "var(--card)",
            border: "1px solid var(--line)",
            borderRadius: 22,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              padding: "16px 20px 12px",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <h2 style={{ fontSize: 15.5, fontWeight: 600 }}>
              {challenge.video.title}
            </h2>
            <span style={{ fontSize: 12.5, color: "var(--ink-soft)" }}>
              {challenge.video.channel}
            </span>
          </div>

          {/* Player */}
          <div
            style={{
              position: "relative",
              width: "100%",
              aspectRatio: "16/9",
              background: "#171310",
            }}
          >
            {ytError && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#CBB9A6",
                  fontSize: 13.5,
                  textAlign: "center",
                  padding: 20,
                  lineHeight: 1.8,
                }}
              >
                {ytError}
              </div>
            )}
            <div id="yt-player" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
          </div>

          {/* Segment track */}
          <div style={{ padding: "16px 20px 20px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 11.5,
                color: "var(--ink-soft)",
                marginBottom: 8,
                letterSpacing: ".04em",
              }}
            >
              <span>SENTENCE TRACK — 點選片段即循環播放</span>
              <span style={{ fontFamily: '"IBM Plex Mono", monospace' }}>
                {fmt(winStart)} – {fmt(winEnd)}
              </span>
            </div>
            <div
              style={{
                position: "relative",
                height: 46,
                background: "#FBF4EC",
                border: "1px solid var(--line)",
                borderRadius: 12,
                overflow: "hidden",
              }}
            >
              {/* Playhead */}
              {playheadPct !== null && (
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    width: 2,
                    background: "var(--orange)",
                    left: `${playheadPct}%`,
                    pointerEvents: "none",
                  }}
                />
              )}
              {/* Segments */}
              {sentences.map((s, i) => {
                const span = winEnd - winStart;
                const left = ((s.start - winStart) / span) * 100;
                const width = ((s.end - s.start) / span) * 100;
                const active = loopSeg === i;
                return (
                  <div
                    key={i}
                    onClick={() => handleLoopToggle(i)}
                    style={{
                      position: "absolute",
                      top: 7,
                      bottom: 7,
                      left: `${left}%`,
                      width: `${width}%`,
                      borderRadius: 8,
                      cursor: "pointer",
                      background: active ? "var(--ink)" : "var(--peach)",
                      border: `1px solid ${active ? "var(--ink)" : "var(--peach-deep)"}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontFamily: '"IBM Plex Mono", monospace',
                      fontSize: 11.5,
                      color: active ? "#FAF1E8" : "var(--ink-soft)",
                      fontWeight: active ? 500 : 400,
                      transition: "all .15s",
                    }}
                  >
                    S{s.idx}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Sentence cards */}
      {sentences.map((s, i) => (
        <SentenceCard
          key={`${date}-${i}`}
          sentence={s}
          sentenceIndex={i}
          date={date}
          isActive={loopSeg === i}
          isLooping={loopSeg === i}
          isPlaying={isPlaying}
          existingRecordings={recordings}
          onLoopToggle={() => handleLoopToggle(i)}
          onPauseToggle={handlePauseToggle}
          onTimeAdjust={(field, delta) => handleTimeAdjust(i, field, delta)}
          onRecordingAdded={handleRecordingAdded}
          onToast={onToast}
        />
      ))}

      {/* Check-in bar */}
      <div
        style={{
          marginTop: 18,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "var(--peach)",
          borderRadius: 22,
          padding: "16px 22px",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <p style={{ fontSize: 13.5 }}>
          {checkinRec
            ? isToday
              ? "今天的挑戰已完成，明天見！"
              : "這一天的挑戰已完成。"
            : needCount > 0 && doneCount >= needCount
            ? isToday
              ? "3 句皆已錄音，可以打卡了！"
              : "3 句皆已錄音，可以補打卡了！"
            : `完成 3 句各至少一次錄音後${isToday ? "即可打卡" : "才能補打卡"}（目前 ${doneCount}/${needCount || "?"}）。`}
        </p>
        <button
          disabled={!canCheckin}
          onClick={handleCheckin}
          style={{
            padding: "12px 26px",
            fontSize: 14,
            background: checkinRec ? "var(--ok)" : canCheckin ? "var(--ink)" : "var(--ink)",
            border: `1px solid ${checkinRec ? "var(--ok)" : "var(--ink)"}`,
            color: "#FAF1E8",
            borderRadius: 999,
            cursor: canCheckin ? "pointer" : "default",
            fontFamily: "inherit",
            fontWeight: 500,
            opacity: !canCheckin && !checkinRec ? 0.4 : 1,
          }}
        >
          {checkinRec
            ? checkinRec.makeup
              ? "已補打卡 ✓"
              : isToday
              ? "今日已打卡 ✓"
              : "當日已完成 ✓"
            : isToday
            ? "完成今日挑戰 →"
            : `補打卡 ${zhDate(date)} →`}
        </button>
      </div>
    </div>
  );
}
