"use client";

import { useState, useRef } from "react";
import { Sentence } from "@/lib/demoData";
import { addRecording, deleteRecording, putTweak, Recording } from "@/lib/supabase";

interface Props {
  sentence: Sentence;
  sentenceIndex: number;
  date: string;
  isActive: boolean;
  isLooping: boolean;
  isPlaying: boolean;
  existingRecordings: Recording[];
  onLoopToggle: () => void;
  onPauseToggle: () => void;
  onTimeAdjust: (field: "start" | "end", delta: number) => void;
  onRecordingAdded: (rec: Recording, blobUrl: string) => void;
  onRecordingDeleted: (recId: string) => void;
  onToast: (msg: string) => void;
}

const fmt = (s: number) =>
  `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(
    Math.floor(s % 60)
  ).padStart(2, "0")}.${Math.floor((s * 10) % 10)}`;

export default function SentenceCard({
  sentence,
  sentenceIndex,
  date,
  isActive,
  isLooping,
  isPlaying,
  existingRecordings,
  onLoopToggle,
  onPauseToggle,
  onTimeAdjust,
  onRecordingAdded,
  onRecordingDeleted,
  onToast,
}: Props) {
  const [showZh, setShowZh] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const myRecordings = existingRecordings.filter(
    (r) => r.sentence_idx === sentenceIndex
  );

  async function toggleRecording() {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      onToast("此環境不支援錄音");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
    } catch {
      onToast("無法取得麥克風權限");
      return;
    }

    // Pick a MIME type supported by the current browser (iOS only supports mp4/aac)
    const preferredTypes = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
    const mimeType = preferredTypes.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
    const mr = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    const chunks: BlobPart[] = [];
    mr.ondataavailable = (e) => chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setIsRecording(false);
      const blob = new Blob(chunks, {
        type: mr.mimeType || "audio/webm",
      });
      try {
        const rec = await addRecording(date, sentenceIndex, blob);
        const blobUrl = URL.createObjectURL(blob);
        onRecordingAdded(rec, blobUrl);
        onToast(`Sentence ${sentenceIndex + 1} 錄音完成（已存入雲端）`);
      } catch (e) {
        console.error(e);
        onToast("錄音上傳失敗，請稍後再試");
      }
    };

    mediaRecorderRef.current = mr;
    mr.start();
    setIsRecording(true);
  }

  async function handleDelete(rec: Recording) {
    setDeletingId(rec.id);
    try {
      await deleteRecording(rec.id, rec.storage_path);
      onRecordingDeleted(rec.id);
    } catch {
      onToast("刪除失敗，請稍後再試");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleTimeAdjust(field: "start" | "end", delta: number) {
    onTimeAdjust(field, delta);
    // sentence.start/end are updated by parent via onTimeAdjust; use predicted values here
    const newStart =
      field === "start"
        ? Math.max(0, +(sentence.start + delta).toFixed(1))
        : sentence.start;
    const newEnd =
      field === "end" ? +(sentence.end + delta).toFixed(1) : sentence.end;
    try {
      await putTweak(date, sentenceIndex, newStart, newEnd);
    } catch {
      // non-critical
    }
  }

  return (
    <div
      style={{
        background: "var(--card)",
        border: `1px solid ${isActive ? "var(--ink)" : "var(--line)"}`,
        boxShadow: isActive ? "0 4px 18px rgba(27,27,27,.06)" : "none",
        borderRadius: 22,
        marginTop: 14,
        padding: "22px 24px",
        transition: "border-color .15s, box-shadow .15s",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: 11,
            color: "var(--orange)",
            background: "#FCEFE3",
            borderRadius: 999,
            padding: "2px 12px",
            letterSpacing: ".06em",
          }}
        >
          SENTENCE {sentence.idx}
        </span>
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: 11.5,
            color: "var(--ink-soft)",
          }}
        >
          {fmt(sentence.start)} → {fmt(sentence.end)}
        </span>
        <span
          style={{
            display: "inline-flex",
            gap: 4,
            alignItems: "center",
            fontSize: 11.5,
            color: "var(--ink-soft)",
          }}
        >
          微調
          {(
            [
              { field: "start" as const, delta: -0.5, label: "S−", title: "起點 -0.5s" },
              { field: "start" as const, delta:  0.5, label: "S+", title: "起點 +0.5s" },
              { field: "end"   as const, delta: -0.5, label: "E−", title: "終點 -0.5s" },
              { field: "end"   as const, delta:  0.5, label: "E+", title: "終點 +0.5s" },
            ]
          ).map(({ field, delta, label, title }) => (
            <button
              key={label}
              title={title}
              onClick={() => handleTimeAdjust(field, delta)}
              style={{
                border: "1px solid var(--line)",
                background: "#FBF4EC",
                borderRadius: 6,
                cursor: "pointer",
                fontFamily: '"IBM Plex Mono", monospace',
                fontSize: 10.5,
                padding: "2px 7px",
                color: "var(--ink)",
              }}
            >
              {label}
            </button>
          ))}
        </span>
      </div>

      {/* Sentence text */}
      <p
        style={{
          fontFamily: '"Newsreader", Georgia, serif',
          fontSize: 22.5,
          lineHeight: 1.5,
          fontWeight: 500,
          letterSpacing: ".004em",
          marginBottom: 8,
        }}
      >
        {sentence.text}
      </p>

      {/* Chinese translation */}
      {showZh && (
        <p
          style={{
            fontSize: 14.5,
            color: "var(--ink-soft)",
            marginBottom: 10,
            fontFamily: '"Noto Sans TC", sans-serif',
          }}
        >
          {sentence.zh}
        </p>
      )}

      {/* Keywords */}
      <div
        style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}
      >
        {sentence.kw.map((k, ki) => (
          <span
            key={ki}
            style={{
              fontSize: 12,
              background: "#FBF4EC",
              color: "var(--ink)",
              border: "1px solid var(--line)",
              borderRadius: 999,
              padding: "2px 12px",
            }}
          >
            {k.w}
            <i style={{ fontStyle: "normal", color: "var(--ink-soft)", marginLeft: 6 }}>
              {k.zh}
            </i>
          </span>
        ))}
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {/* Loop button */}
        <button
          onClick={onLoopToggle}
          style={{
            border: `1px solid ${isLooping ? "var(--orange)" : "var(--line)"}`,
            background: isLooping ? "#FCEFE3" : "var(--card)",
            color: isLooping ? "#B65E1F" : "var(--ink)",
            padding: "8px 18px",
            fontSize: 13,
            fontFamily: "inherit",
            borderRadius: 999,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            fontWeight: isLooping ? 600 : 500,
            transition: "all .15s",
          }}
        >
          {isLooping ? "◼ 停止循環" : "↻ 循環播放"}
        </button>

        {/* Pause/play button */}
        <button
          onClick={onPauseToggle}
          style={{
            border: "1px solid var(--line)",
            background: "var(--card)",
            color: "var(--ink)",
            padding: "8px 18px",
            fontSize: 13,
            fontFamily: "inherit",
            borderRadius: 999,
            cursor: "pointer",
            fontWeight: 500,
            transition: "all .15s",
          }}
        >
          {isPlaying ? "⏸ 暫停" : "▶ 繼續"}
        </button>

        {/* Translation toggle */}
        <button
          onClick={() => setShowZh((v) => !v)}
          style={{
            border: "1px solid var(--line)",
            background: "var(--card)",
            color: "var(--ink)",
            padding: "8px 18px",
            fontSize: 13,
            fontFamily: "inherit",
            borderRadius: 999,
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          中譯
        </button>

        {/* Record button */}
        <button
          onClick={toggleRecording}
          style={{
            border: `1px solid ${isRecording ? "var(--orange)" : "var(--line)"}`,
            background: isRecording ? "var(--orange)" : "var(--card)",
            color: isRecording ? "#fff" : "var(--ink)",
            padding: "8px 18px",
            fontSize: 13,
            fontFamily: "inherit",
            borderRadius: 999,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            fontWeight: 500,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: isRecording ? "#fff" : "var(--orange)",
              animation: isRecording ? "pulse 1s infinite" : "none",
            }}
          />
          {isRecording ? "停止錄音" : "開始錄音"}
        </button>
      </div>

      {/* Recordings list */}
      {myRecordings.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4
            style={{
              fontSize: 12,
              color: "var(--ink-soft)",
              fontWeight: 500,
              marginBottom: 6,
              letterSpacing: ".04em",
            }}
          >
            MY RECORDINGS
          </h4>
          {myRecordings.map((rec) => {
            const d = new Date(rec.created_at);
            const label = `${String(d.getMonth() + 1).padStart(2, "0")}/${String(
              d.getDate()
            ).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(
              d.getMinutes()
            ).padStart(2, "0")}`;
            const isDeleting = deletingId === rec.id;
            return (
              <div
                key={rec.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "7px 0",
                  borderTop: "1px solid var(--line)",
                  flexWrap: "wrap",
                  opacity: isDeleting ? 0.4 : 1,
                }}
              >
                <span
                  style={{
                    fontFamily: '"IBM Plex Mono", monospace',
                    fontSize: 11.5,
                    color: "var(--ink-soft)",
                    minWidth: 118,
                  }}
                >
                  {label}
                </span>
                {rec.signedUrl ? (
                  <audio
                    controls
                    src={rec.signedUrl}
                    style={{ height: 32, maxWidth: 260, flex: 1, minWidth: 170 }}
                  />
                ) : (
                  <span style={{ fontSize: 12, color: "#B65E1F" }}>
                    無法載入（請重新整理頁面）
                  </span>
                )}
                <button
                  onClick={() => handleDelete(rec)}
                  disabled={isDeleting}
                  title="刪除錄音"
                  style={{
                    border: "none",
                    background: "none",
                    cursor: isDeleting ? "default" : "pointer",
                    color: "var(--ink-soft)",
                    padding: "4px 6px",
                    borderRadius: 6,
                    fontSize: 15,
                    lineHeight: 1,
                    flexShrink: 0,
                  }}
                >
                  🗑
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
