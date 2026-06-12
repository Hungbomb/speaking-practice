export interface Keyword {
  w: string;
  zh: string;
}

export interface Sentence {
  idx: number;
  start: number;
  end: number;
  text: string;
  zh: string;
  kw: Keyword[];
}

export interface Video {
  youtube_id: string;
  title: string;
  channel: string;
}

export interface Challenge {
  video: Video;
  sentences: Sentence[];
}

export const LIBRARY: Challenge[] = [
  {
    video: {
      youtube_id: "arj7oStGLkU",
      title: "Inside the mind of a master procrastinator",
      channel: "TED · Tim Urban",
    },
    sentences: [
      {
        idx: 1,
        start: 11.8,
        end: 17.3,
        text: "So in college, I was a government major, which means I had to write a lot of papers.",
        zh: "大學時我主修政治，這代表我得寫一大堆報告。",
        kw: [{ w: "government major", zh: "主修政治／政府學" }],
      },
      {
        idx: 2,
        start: 17.3,
        end: 23.5,
        text: "Now, when a normal student writes a paper, they might spread the work out a little like this.",
        zh: "一般學生寫報告時，可能會像這樣把工作量平均分配。",
        kw: [{ w: "spread out", zh: "分散、攤開（工作量）" }],
      },
      {
        idx: 3,
        start: 23.5,
        end: 34.5,
        text: "So, you know — you get started maybe a little slowly, but you get enough done in the first week that, with some heavier days later on, everything gets done, things stay civil.",
        zh: "你知道的——開頭也許慢一點，但第一週完成得夠多，之後幾天再加把勁，一切就能完成，過程也不至於失控。",
        kw: [
          { w: "heavier days", zh: "工作量較重的日子" },
          { w: "stay civil", zh: "維持體面／不失控" },
        ],
      },
    ],
  },
  {
    video: {
      youtube_id: "eIho2S0ZahI",
      title: "How to speak so that people want to listen",
      channel: "TED · Julian Treasure",
    },
    sentences: [
      {
        idx: 1,
        start: 14.0,
        end: 18.0,
        text: "The human voice: it's the instrument we all play.",
        zh: "人類的聲音，是我們每個人都在演奏的樂器。",
        kw: [{ w: "instrument", zh: "樂器；工具" }],
      },
      {
        idx: 2,
        start: 18.0,
        end: 24.0,
        text: "It's the most powerful sound in the world, probably. It's the only one that can start a war or say 'I love you.'",
        zh: "它大概是世上最有力量的聲音——唯一能發動一場戰爭、也能說出「我愛你」的聲音。",
        kw: [{ w: "powerful", zh: "有力量的" }],
      },
      {
        idx: 3,
        start: 24.0,
        end: 28.2,
        text: "And yet many people have the experience that when they speak, people don't listen to them.",
        zh: "然而許多人都有這樣的經驗：自己說話時，別人並沒有在聽。",
        kw: [{ w: "and yet", zh: "然而、儘管如此" }],
      },
    ],
  },
  {
    video: {
      youtube_id: "iCvmsMzlF7o",
      title: "The power of vulnerability",
      channel: "TED · Brené Brown",
    },
    sentences: [
      {
        idx: 1,
        start: 15.0,
        end: 21.0,
        text: "So, I'll start with this: a couple years ago, an event planner called me because I was going to do a speaking event.",
        zh: "就從這件事說起：幾年前，一位活動企劃打給我，因為我即將出席一場演講活動。",
        kw: [{ w: "event planner", zh: "活動企劃" }],
      },
      {
        idx: 2,
        start: 21.0,
        end: 27.0,
        text: "And she called, and she said, 'I'm really struggling with how to write about you on the little flyer.'",
        zh: "她打來說：「我真的很苦惱，不知道該怎麼在小傳單上介紹你。」",
        kw: [
          { w: "struggle with", zh: "為…苦惱、掙扎" },
          { w: "flyer", zh: "傳單" },
        ],
      },
      {
        idx: 3,
        start: 27.0,
        end: 29.8,
        text: "And I thought, 'Well, what's the struggle?'",
        zh: "我心想：「嗯，這有什麼好苦惱的？」",
        kw: [{ w: "the struggle", zh: "困難點、糾結之處" }],
      },
    ],
  },
];

export function challengeFor(dateISO: string): Challenge {
  const n = dateISO.split("-").reduce((a, b) => a + Number(b), 0);
  return JSON.parse(JSON.stringify(LIBRARY[n % LIBRARY.length]));
}
