"use client";

import { useState } from "react";

interface CheckinRecord {
  makeup: boolean;
}

interface Props {
  checkinMap: Map<string, CheckinRecord>;
  today: string;
  onLoadDate: (date: string) => void;
  onSwitchTab: (tab: "practice") => void;
}

const z2 = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) =>
  `${d.getFullYear()}-${z2(d.getMonth() + 1)}-${z2(d.getDate())}`;

export default function CalendarView({
  checkinMap,
  today,
  onLoadDate,
  onSwitchTab,
}: Props) {
  const todayDate = new Date(today + "T00:00:00");
  const [calY, setCalY] = useState(todayDate.getFullYear());
  const [calM, setCalM] = useState(todayDate.getMonth());

  function prevMonth() {
    if (calM === 0) { setCalY((y) => y - 1); setCalM(11); }
    else setCalM((m) => m - 1);
  }
  function nextMonth() {
    if (calM === 11) { setCalY((y) => y + 1); setCalM(0); }
    else setCalM((m) => m + 1);
  }

  const prefix = `${calY}-${z2(calM + 1)}`;
  const inMonth = [...checkinMap.keys()].filter((k) => k.startsWith(prefix));
  const makeupCount = inMonth.filter((k) => checkinMap.get(k)!.makeup).length;

  const firstDay = new Date(calY, calM, 1).getDay();
  const daysInMonth = new Date(calY, calM + 1, 0).getDate();

  const days: ({ date: string; d: number } | null)[] = [];
  for (let i = 0; i < firstDay; i++) days.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    days.push({ date: iso(new Date(calY, calM, d)), d });
  }

  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: 22,
        padding: 24,
        marginTop: 14,
      }}
    >
      {/* Calendar header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 14,
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>
          {calY} 年 {calM + 1} 月
        </h3>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <button
            aria-label="上個月"
            onClick={prevMonth}
            style={{
              border: "1px solid var(--line)",
              background: "var(--card)",
              borderRadius: 999,
              cursor: "pointer",
              fontSize: 14,
              padding: "3px 15px",
              color: "var(--ink)",
            }}
          >
            ‹
          </button>
          <button
            aria-label="下個月"
            onClick={nextMonth}
            style={{
              border: "1px solid var(--line)",
              background: "var(--card)",
              borderRadius: 999,
              cursor: "pointer",
              fontSize: 14,
              padding: "3px 15px",
              color: "var(--ink)",
            }}
          >
            ›
          </button>
        </div>
        <span style={{ fontSize: 12.5, color: "var(--ink-soft)" }}>
          本月 {inMonth.length} 次打卡（含補挑戰 {makeupCount} 次）
        </span>
      </div>

      {/* Day of week headers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(7, 1fr)",
          gap: 7,
        }}
      >
        {["日", "一", "二", "三", "四", "五", "六"].map((d) => (
          <div
            key={d}
            style={{
              fontSize: 11,
              color: "var(--ink-soft)",
              textAlign: "center",
              paddingBottom: 4,
              letterSpacing: ".08em",
            }}
          >
            {d}
          </div>
        ))}

        {/* Day cells */}
        {days.map((day, idx) => {
          if (!day) {
            return (
              <div key={`blank-${idx}`} style={{ aspectRatio: "1" }} />
            );
          }

          const { date, d } = day;
          const rec = checkinMap.get(date);
          const isToday = date === today;
          const isFuture = date > today;
          const isMissed = !rec && !isToday && !isFuture;

          let bg = "#FDFAF6";
          let border = "1px solid var(--line)";
          let color = "var(--ink)";
          let cursor = "pointer";
          let title = "";

          if (rec) {
            if (rec.makeup) {
              bg = "var(--card)";
              border = "1.5px solid var(--orange)";
              color = "var(--orange)";
              title = "回顧這一天";
            } else {
              bg = "var(--ink)";
              border = "1px solid var(--ink)";
              color = "#FAF1E8";
              title = "回顧這一天";
            }
          } else if (isFuture) {
            color = "#D8C9B8";
            cursor = "default";
          } else if (isToday) {
            title = "今日挑戰";
          } else if (isMissed) {
            title = "進行補挑戰";
          }

          return (
            <div
              key={date}
              title={title}
              onClick={() => {
                if (isFuture) return;
                onLoadDate(date);
                onSwitchTab("practice");
              }}
              style={{
                aspectRatio: "1",
                border,
                borderRadius: 14,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: '"IBM Plex Mono", monospace',
                fontSize: 12.5,
                background: bg,
                color,
                cursor,
                outline: isToday ? "2px solid var(--orange)" : "none",
                outlineOffset: isToday ? 2 : 0,
                transition: "all .12s",
                position: "relative",
              }}
              onMouseEnter={(e) => {
                if (isMissed) {
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "var(--orange)";
                  (e.currentTarget as HTMLElement).style.background =
                    "var(--peach)";
                } else if (rec) {
                  (e.currentTarget as HTMLElement).style.transform = "scale(1.05)";
                }
              }}
              onMouseLeave={(e) => {
                if (isMissed) {
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "var(--line)";
                  (e.currentTarget as HTMLElement).style.background = bg;
                } else if (rec) {
                  (e.currentTarget as HTMLElement).style.transform = "scale(1)";
                }
              }}
            >
              {d}
              {isMissed && (
                <span
                  style={{
                    position: "absolute",
                    bottom: 2,
                    fontSize: 8.5,
                    color: "var(--orange)",
                    fontFamily: '"Noto Sans TC", sans-serif',
                    opacity: 0,
                  }}
                  className="missed-label"
                >
                  補
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: 16,
          marginTop: 16,
          fontSize: 12,
          color: "var(--ink-soft)",
          flexWrap: "wrap",
        }}
      >
        {[
          { bg: "var(--ink)", label: "已完成" },
          {
            bg: "#fff",
            border: "1.5px solid var(--orange)",
            label: "補挑戰完成",
          },
          {
            bg: "#FDFAF6",
            border: "1px solid var(--line)",
            label: "未完成",
          },
        ].map(({ bg, border, label }) => (
          <span key={label}>
            <i
              style={{
                display: "inline-block",
                width: 12,
                height: 12,
                borderRadius: 4,
                verticalAlign: -1,
                marginRight: 5,
                background: bg,
                border,
              }}
            />
            {label}
          </span>
        ))}
      </div>

      <p
        style={{ marginTop: 10, fontSize: 12, color: "var(--ink-soft)" }}
      >
        點「已完成」的日期可回顧當天內容與錄音；點「未完成」的日期會載入當天挑戰，
        <b>完成 3 句錄音後才能補打卡</b>。
      </p>
    </div>
  );
}
