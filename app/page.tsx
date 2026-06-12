"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import PracticeView from "@/components/PracticeView";
import CalendarView from "@/components/CalendarView";
import MilestoneView from "@/components/MilestoneView";
import { getCheckins } from "@/lib/supabase";

type Tab = "practice" | "cal";

const z2 = (n: number) => String(n).padStart(2, "0");
function getToday() {
  const d = new Date();
  return `${d.getFullYear()}-${z2(d.getMonth() + 1)}-${z2(d.getDate())}`;
}

export default function Home() {
  const today = getToday();
  const [tab, setTab] = useState<Tab>("practice");
  const [currentDate, setCurrentDate] = useState(today);
  const [checkinMap, setCheckinMap] = useState<Map<string, { makeup: boolean }>>(new Map());
  const [toastMsg, setToastMsg] = useState("");
  const [toastVisible, setToastVisible] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load all checkins on mount
  useEffect(() => {
    getCheckins().then((rows) => {
      const m = new Map<string, { makeup: boolean }>();
      for (const r of rows) m.set(r.date, { makeup: r.makeup });
      setCheckinMap(m);
    });
  }, []);

  const showToast = useCallback((msg: string) => {
    setToastMsg(msg);
    setToastVisible(true);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToastVisible(false), 2600);
  }, []);

  const handleCheckin = useCallback((date: string, makeup: boolean) => {
    setCheckinMap((prev) => {
      const next = new Map(prev);
      next.set(date, { makeup });
      return next;
    });
  }, []);

  const handleLoadDate = useCallback((date: string) => {
    setCurrentDate(date);
    setTab("practice");
  }, []);

  // Compute streak
  const streak = (() => {
    let n = 0;
    const d = new Date(today + "T00:00:00");
    if (!checkinMap.has(getToday())) d.setDate(d.getDate() - 1);
    while (true) {
      const iso = `${d.getFullYear()}-${z2(d.getMonth() + 1)}-${z2(d.getDate())}`;
      if (!checkinMap.has(iso)) break;
      n++;
      d.setDate(d.getDate() - 1);
    }
    return n;
  })();

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "0 18px 90px" }}>
      {/* Header */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "30px 0 20px",
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: "var(--peach)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 22,
            }}
          >
            ☾
          </div>
          <div>
            <h1
              style={{
                fontSize: 19,
                fontWeight: 600,
                letterSpacing: ".01em",
                lineHeight: 1.3,
              }}
            >
              每日口說挑戰
            </h1>
            <small
              style={{
                display: "block",
                fontWeight: 400,
                color: "var(--ink-soft)",
                fontSize: 11,
                letterSpacing: ".14em",
              }}
            >
              DAILY SPEAKING PRACTICE
            </small>
          </div>
        </div>
        <div
          style={{
            background: "var(--card)",
            border: "1px solid var(--line)",
            borderRadius: 999,
            padding: "8px 18px",
            fontSize: 13,
            color: "var(--ink-soft)",
          }}
        >
          連續挑戰{" "}
          <b
            style={{
              color: "var(--ink)",
              fontSize: 16,
              fontFamily: '"IBM Plex Mono", monospace',
              margin: "0 2px",
            }}
          >
            {streak}
          </b>{" "}
          天
        </div>
      </header>

      {/* Tabs */}
      <nav style={{ display: "flex", gap: 8, margin: "6px 0 22px" }}>
        {(
          [
            { id: "practice" as Tab, label: "練習" },
            { id: "cal" as Tab, label: "打卡與里程碑" },
          ] as const
        ).map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              border: "1px solid var(--line)",
              background: tab === id ? "var(--ink)" : "var(--card)",
              color: tab === id ? "#FAF1E8" : "var(--ink-soft)",
              padding: "9px 22px",
              fontSize: 13.5,
              fontFamily: "inherit",
              cursor: "pointer",
              borderRadius: 999,
              fontWeight: 500,
              transition: "all .15s",
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* Practice tab */}
      {tab === "practice" && (
        <PracticeView
          date={currentDate}
          checkinMap={checkinMap}
          today={today}
          onCheckin={handleCheckin}
          onLoadDate={handleLoadDate}
          onToast={showToast}
        />
      )}

      {/* Calendar & milestone tab */}
      {tab === "cal" && (
        <>
          <CalendarView
            checkinMap={checkinMap}
            today={today}
            onLoadDate={handleLoadDate}
            onSwitchTab={(t) => setTab(t)}
          />
          <MilestoneView checkinMap={checkinMap} today={today} />
        </>
      )}

      {/* Toast */}
      <div
        style={{
          position: "fixed",
          bottom: 24,
          left: "50%",
          transform: "translateX(-50%)",
          background: "var(--ink)",
          color: "#FAF1E8",
          padding: "11px 24px",
          borderRadius: 999,
          fontSize: 13.5,
          opacity: toastVisible ? 1 : 0,
          pointerEvents: "none",
          transition: "opacity .25s",
          zIndex: 50,
          maxWidth: "90vw",
          textAlign: "center",
        }}
      >
        {toastMsg}
      </div>
    </div>
  );
}
