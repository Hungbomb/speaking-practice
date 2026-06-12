"use client";

const MILESTONES = [25, 50, 75, 100, 150, 200, 250, 300, 365];

interface Props {
  checkinMap: Map<string, { makeup: boolean }>;
  today: string;
}

export default function MilestoneView({ checkinMap, today }: Props) {
  const todayDate = new Date(today + "T00:00:00");
  const year = todayDate.getFullYear();
  const yearPrefix = String(year);

  const yearCount = [...checkinMap.keys()].filter((k) =>
    k.startsWith(yearPrefix)
  ).length;

  const next = MILESTONES.find((m) => yearCount < m);
  const prev = MILESTONES.filter((m) => m <= yearCount).pop() ?? 0;
  const barPct = next
    ? Math.min(100, ((yearCount - prev) / (next - prev)) * 100)
    : 100;

  return (
    <>
      {/* Year milestones */}
      <div
        style={{
          background: "var(--card)",
          border: "1px solid var(--line)",
          borderRadius: 22,
          padding: 24,
          marginTop: 14,
        }}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>
          {year} 年度里程碑
        </h3>
        <p
          style={{
            fontSize: 12.5,
            color: "var(--ink-soft)",
            marginBottom: 18,
          }}
        >
          今年累計打卡{" "}
          <b
            style={{
              color: "var(--orange)",
              fontFamily: '"IBM Plex Mono", monospace',
              fontSize: 14,
            }}
          >
            {yearCount}
          </b>{" "}
          天（含補挑戰）
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(92px, 1fr))",
            gap: "18px 10px",
          }}
        >
          {MILESTONES.map((m) => {
            const got = yearCount >= m;
            return (
              <div key={m} style={{ textAlign: "center" }}>
                <div
                  style={{
                    width: 76,
                    height: 76,
                    borderRadius: "50%",
                    margin: "0 auto 8px",
                    position: "relative",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    border: got
                      ? "1.5px solid var(--gold)"
                      : "1.5px dashed #E6D5C0",
                    background: got
                      ? "radial-gradient(circle at 32% 26%, #FFF8E8, #F6E3BC 62%, #EBCB8E)"
                      : "#FDFAF6",
                    color: got ? "#7A5A1E" : "#CBB9A2",
                    boxShadow: got
                      ? "0 3px 12px rgba(201,150,63,.22)"
                      : "none",
                  }}
                >
                  {got && (
                    <div
                      style={{
                        position: "absolute",
                        inset: 5,
                        borderRadius: "50%",
                        border: "1px solid rgba(201,150,63,.55)",
                        pointerEvents: "none",
                      }}
                    />
                  )}
                  <span style={{ fontSize: 11, lineHeight: 1, marginBottom: 1 }}>
                    {got ? "✦" : "☾"}
                  </span>
                  <span
                    style={{
                      fontFamily: '"Newsreader", Georgia, serif',
                      fontSize: 21,
                      fontWeight: 500,
                      lineHeight: 1.05,
                    }}
                  >
                    {m}
                  </span>
                  <span
                    style={{
                      fontSize: 9.5,
                      letterSpacing: ".2em",
                      fontFamily: '"Noto Sans TC", sans-serif',
                    }}
                  >
                    天
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 11.5,
                    color: got ? "var(--ink)" : "var(--ink-soft)",
                    fontWeight: got ? 500 : 400,
                  }}
                >
                  {got ? "已達成" : ""}
                </div>
                {!got && (
                  <div
                    style={{
                      fontSize: 10.5,
                      color: "#CBB9A2",
                      fontFamily: '"IBM Plex Mono", monospace',
                    }}
                  >
                    {yearCount}/{m}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Progress bar */}
        <div
          style={{
            height: 6,
            background: "#F3E8DA",
            borderRadius: 3,
            overflow: "hidden",
            margin: "18px 0 6px",
          }}
        >
          <div
            style={{
              height: "100%",
              background:
                "linear-gradient(90deg, var(--gold-soft), var(--gold))",
              borderRadius: 3,
              width: `${barPct}%`,
              transition: "width .6s ease",
            }}
          />
        </div>
        <p
          style={{
            fontSize: 12,
            color: "var(--ink-soft)",
            textAlign: "right",
          }}
        >
          {next
            ? `距離下一枚徽章（${next} 天）還差 ${next - yearCount} 天`
            : "本年度全部徽章已收集完成 ✦"}
        </p>
      </div>

      {/* Monthly perfect attendance */}
      <div
        style={{
          background: "var(--card)",
          border: "1px solid var(--line)",
          borderRadius: 22,
          padding: 24,
          marginTop: 14,
        }}
      >
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>每月全勤</h3>
        <p
          style={{
            fontSize: 12.5,
            color: "var(--ink-soft)",
            marginBottom: 18,
          }}
        >
          當月每一天都完成挑戰（含補挑戰），即獲得該月金牌
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(68px, 1fr))",
            gap: "14px 8px",
          }}
        >
          {Array.from({ length: 12 }, (_, m) => {
            const daysInMonth = new Date(year, m + 1, 0).getDate();
            let hit = 0;
            for (let d = 1; d <= daysInMonth; d++) {
              const dateISO = `${year}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
              if (checkinMap.has(dateISO)) hit++;
            }
            const perfect = hit === daysInMonth;
            const isFuture = m > todayDate.getMonth();

            return (
              <div
                key={m}
                style={{
                  textAlign: "center",
                  opacity: isFuture ? 0.45 : 1,
                }}
              >
                <div
                  style={{
                    width: 52,
                    height: 52,
                    borderRadius: "50%",
                    margin: "0 auto 6px",
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: '"Newsreader", Georgia, serif',
                    fontSize: perfect ? 18 : 14,
                    border: perfect
                      ? "1.5px solid var(--gold)"
                      : "1.5px dashed #E6D5C0",
                    background: perfect
                      ? "radial-gradient(circle at 32% 26%, #FFF8E8, #F6E3BC 62%, #EBCB8E)"
                      : "#FDFAF6",
                    color: perfect ? "#7A5A1E" : "#CBB9A2",
                    boxShadow: perfect
                      ? "0 2px 8px rgba(201,150,63,.22)"
                      : "none",
                  }}
                >
                  {perfect && (
                    <div
                      style={{
                        position: "absolute",
                        inset: 4,
                        borderRadius: "50%",
                        border: "1px solid rgba(201,150,63,.55)",
                      }}
                    />
                  )}
                  {perfect ? "✦" : m + 1}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: perfect ? "var(--ink)" : "var(--ink-soft)",
                    fontWeight: perfect ? 500 : 400,
                  }}
                >
                  {m + 1} 月
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: "#CBB9A2",
                    fontFamily: '"IBM Plex Mono", monospace',
                  }}
                >
                  {isFuture ? "—" : `${hit}/${daysInMonth}`}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
