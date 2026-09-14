// events.js — 隨機事件系統（events.md）
// ctx: 由 state.js 於行動結算後組成，內容包含 { type:'training'|'rest'|'race', stage, stat?, intensity?, race?:{grade,placement,fieldSize,prize,rep} }
"use strict";

function addBuff(career, buff) {
  career.activeBuffs = career.activeBuffs || [];
  career.activeBuffs.push(buff);
}

function pruneBuffs(career, turn) {
  career.activeBuffs = (career.activeBuffs || []).filter((b) => {
    if (b.scope === "nextRaceOnly") return true;
    if (b.scope && b.scope.expiresAtTurn !== undefined) return b.scope.expiresAtTurn >= turn;
    return true;
  });
}

// ---------- 一般事件：正面 ----------
const GENERAL_POSITIVE = [
  {
    id: "sudden_realization", name: "突然醒悟", category: "positive",
    text: "今天的訓練中，牠突然抓住了奔跑的訣竅，動作變得更流暢了。",
    cond: (s, ctx) => ctx.stage === "growth" && ctx.type === "training",
    effect: (s, ctx) => { addStatPermanent(s.currentRun.horse, ctx.stat, 8); s.currentRun.career.fatigue = clamp(s.currentRun.career.fatigue - 5, 0, FATIGUE_CAP); },
  },
  {
    id: "gained_attention", name: "獲得關注", category: "positive",
    text: "一位資深馬主在賽後找上了你，眼神裡滿是讚賞，並決定提供一些資助。",
    cond: (s, ctx) => ctx.type === "race" && ctx.race && ctx.race.placement <= 3,
    effect: (s) => { s.currentRun.career.reputation += 15; s.currentRun.career.money += 500; },
  },
  {
    id: "natural_talent", name: "天賦異稟", category: "positive",
    text: "第一次正式訓練，牠展現出超乎預期的天賦。",
    cond: (s, ctx) => ctx.type === "training" && ctx.isFirstTraining,
    effect: (s, ctx) => {
      addStatPermanent(s.currentRun.horse, ctx.stat, 5);
      s.currentRun.career.talentBuff = { stat: ctx.stat, amount: 2, expiresAtTurn: s.currentRun.career.turn + 4 };
    },
  },
  {
    id: "sponsor_invite", name: "贊助商邀約", category: "positive",
    text: "一家飼料品牌找上門，想贊助牠出賽下一場指定賽事。",
    cond: (s, ctx) => (ctx.stage === "growth" || ctx.stage === "peak") && ctx.type === "race",
    effect: (s) => { s.currentRun.career.money += 800; },
  },
  {
    id: "great_condition", name: "狀態絕佳", category: "positive",
    text: "這幾天休養得特別好，精神狀態出奇地好。",
    cond: (s, ctx) => ctx.type === "rest",
    effect: (s) => { const c = s.currentRun.career; c.energy = clamp(c.energy + 10, 0, ENERGY_CAP); c.fatigue = clamp(c.fatigue - 10, 0, FATIGUE_CAP); },
  },
  {
    id: "fan_support", name: "粉絲應援", category: "positive",
    text: "場邊的加油聲讓牠格外亢奮。（下一場比賽生效）",
    cond: () => true,
    effect: (s) => addBuff(s.currentRun.career, { target: "luck", amount: 3, scope: "nextRaceOnly" }),
  },
  {
    id: "advice_absorbed", name: "吸收建議", category: "positive",
    text: "資深調教師的一席話讓訓練效率大增。",
    cond: (s, ctx) => ctx.stage === "peak" && ctx.type === "training",
    effect: (s) => { s.currentRun.career.fatigue = clamp(s.currentRun.career.fatigue - 15, 0, FATIGUE_CAP); },
  },
  {
    id: "pace_partner", name: "破風搭檔", category: "positive",
    text: "這場比賽的節奏抓得恰到好處，牠似乎摸清了訣竅。",
    cond: (s, ctx) => ctx.type === "race" && ctx.race && ctx.race.placement <= 3,
    effect: (s) => addStatPermanent(s.currentRun.horse, "luck", 2),
  },
  {
    id: "vacation", name: "假期休養", category: "positive",
    text: "難得的悠閒時光，牠徹底放鬆了下來。",
    cond: (s, ctx) => ctx.type === "rest",
    effect: (s) => { const c = s.currentRun.career; c.energy = ENERGY_CAP; c.fatigue = clamp(c.fatigue - 30, 0, FATIGUE_CAP); },
  },
  {
    id: "good_weather", name: "天時地利", category: "positive",
    text: "晴朗的天氣讓牠跑得格外輕快。（下一場比賽生效）",
    cond: () => true,
    effect: (s) => addBuff(s.currentRun.career, { target: "speed", amount: 5, scope: "nextRaceOnly" }),
  },
  {
    id: "transformation", name: "蛻變成長", category: "positive",
    text: "持續的專項特訓終於開花結果。",
    cond: (s, ctx) => ctx.stage === "growth" && ctx.type === "training" && s.currentRun.career.trainingStreak.count >= 4,
    effect: (s, ctx) => addStatPermanent(s.currentRun.horse, ctx.stat, 10),
  },
];

// ---------- 一般事件：負面 ----------
const GENERAL_NEGATIVE = [
  {
    id: "cold", name: "生病感冒", category: "negative",
    text: "牠這幾天看起來有點沒精神。（下一場比賽速度暫時-5）",
    cond: (s, ctx) => ctx.type === "training",
    effect: (s) => addBuff(s.currentRun.career, { target: "speed", amount: -5, scope: "nextRaceOnly" }),
  },
  {
    id: "old_injury", name: "舊傷復發", category: "negative",
    text: "比賽後牠的步伐出現了些微異常。",
    cond: (s, ctx) => ctx.type === "race",
    effect: (s) => { const c = s.currentRun.career; c.fatigue = clamp(c.fatigue + 15, 0, FATIGUE_CAP); c.injuryRiskBonusNextTurn = 0.10; },
  },
  {
    id: "pre_race_nerves", name: "賽前緊張", category: "negative",
    text: "出場前牠顯得有些焦躁不安。（下一場比賽生效）",
    cond: () => true,
    effect: (s) => addBuff(s.currentRun.career, { target: "luck", amount: -5, scope: "nextRaceOnly" }),
  },
  {
    id: "overtraining", name: "過度訓練", category: "negative",
    text: "高強度的訓練似乎讓牠有點吃不消。",
    cond: (s, ctx) => ctx.type === "training" && ctx.intensity === "intense",
    effect: (s) => { s.currentRun.career.fatigue = clamp(s.currentRun.career.fatigue + 10, 0, FATIGUE_CAP); },
  },
  {
    id: "bad_weather", name: "天氣不佳", category: "negative",
    text: "濕滑的賽道讓體力消耗得特別快。（下一場比賽生效）",
    cond: () => true,
    effect: (s) => addBuff(s.currentRun.career, { target: "enduranceCoef", amount: 1.2, scope: "nextRaceOnly" }),
  },
  {
    id: "low_morale", name: "士氣低落", category: "negative",
    text: "一成不變的訓練內容讓牠提不起勁。",
    cond: (s, ctx) => ctx.type === "training" && s.currentRun.career.trainingStreak.count >= 2,
    effect: (s, ctx) => {
      if (ctx.growthApplied) {
        const horse = s.currentRun.horse;
        horse.stats[ctx.stat] = clamp(horse.stats[ctx.stat] - ctx.growthApplied * 0.2, STAT_FLOOR, effectiveStatCap(horse));
      }
    },
  },
  {
    id: "race_mistake", name: "比賽失誤", category: "negative",
    text: "比賽途中一個踉蹌，打亂了原本的節奏。",
    cond: (s, ctx) => ctx.type === "race" && ctx.race,
    effect: (s, ctx) => { ctx.race.mistakeApplied = true; },
  },
  {
    id: "media_pressure", name: "媒體壓力", category: "negative",
    text: "不理想的戰績引來了外界的質疑聲浪。",
    cond: (s, ctx) => ctx.stage === "peak" && ctx.type === "race" && ctx.race && ctx.race.placement > Math.ceil(ctx.race.fieldSize / 2),
    effect: (s) => { s.currentRun.career.reputation = Math.max(0, s.currentRun.career.reputation - 10); },
  },
];

// ---------- 一般事件：中立 ----------
const GENERAL_NEUTRAL = [
  { id: "stable_fun", name: "馬廄趣事", category: "neutral", text: "隔壁馬廄的老馬跟牠似乎處得不錯。", cond: () => true, effect: () => {} },
  { id: "new_feed", name: "新料嘗試", category: "neutral", text: "馬廄換了新的飼料配方給牠試試。", cond: () => true, effect: () => {} },
  { id: "visit_veteran", name: "拜訪老馬", category: "neutral", text: "一匹退役的前輩馬來訪，牠似乎很感興趣。", cond: () => true, effect: () => {} },
  { id: "staff_change", name: "人員更換", category: "neutral", text: "這個月開始由另一位訓練師負責日常照顧。", cond: () => true, effect: () => {} },
  { id: "weather_watch", name: "天氣觀察", category: "neutral", text: "調教師提醒，接下來幾天可能會下雨。", cond: () => true, effect: () => {} },
];

const GENERAL_CATEGORIES = [
  { list: GENERAL_POSITIVE, totalProb: 0.1575 },
  { list: GENERAL_NEGATIVE, totalProb: 0.1225 },
  { list: GENERAL_NEUTRAL, totalProb: 0.07 },
];
const GENERAL_LAYER_TOTAL = 0.35;

// ---------- 稀有正面事件 ----------
const RARE_POSITIVE = [
  {
    id: "awakening", name: "覺醒時刻", category: "rare-positive", baseProb: 0.004,
    text: "深藏的潛力似乎在這一刻甦醒了，牠的極限又更進了一步。",
    cond: () => true,
    effect: (s) => { s.currentRun.horse.statCapBonus = (s.currentRun.horse.statCapBonus || 0) + 10; },
  },
  {
    id: "breakout_star", name: "一戰成名", category: "rare-positive", baseProb: 0.005,
    text: "一場誰也沒料到的驚豔演出，讓牠一夜之間成為賽場話題焦點。",
    cond: (s, ctx) => ctx.type === "race" && ctx.race,
    effect: (s, ctx) => { s.currentRun.career.reputation += 50; if (ctx.race) ctx.race.doublePrize = true; },
  },
  {
    id: "extra_sponsor", name: "額外贊助", category: "rare-positive", baseProb: 0.006,
    text: "一位神秘人士看中了牠的潛力，捐贈了一筆可觀的資金。",
    cond: () => true,
    effect: (s) => { s.currentRun.career.money += 2000; },
  },
  {
    id: "perfect_condition", name: "完美體態", category: "rare-positive", baseProb: 0.005,
    text: "這是牠這輩子最好的狀態，彷彿感受不到絲毫疲憊。",
    cond: () => true,
    effect: (s) => {
      const c = s.currentRun.career;
      c.fatigue = 0; c.energy = ENERGY_CAP;
      addBuff(c, { target: "luck", amount: 15, scope: "nextRaceOnly" });
    },
  },
];
const RARE_POSITIVE_TOTAL = 0.02;

// ---------- 稀有提前結束事件 ----------
const RARE_ENDING = [
  { id: "major_injury", name: "重大傷病", baseProb: 0.003, text: "一次意外的重傷，讓牠的賽場生涯就此畫下句點。", reason: "重大傷病", cond: () => true, effect: () => {} },
  { id: "natural_disaster", name: "天災意外", baseProb: 0.002, text: "一場無法預料的意外，打斷了原本的生涯規劃。", reason: "天災意外", cond: () => true, effect: () => {} },
  { id: "scandal", name: "醜聞風波", baseProb: 0.0015, text: "一場突如其來的爭議，讓馬主決定撤資退役。", reason: "醜聞風波", cond: () => true, effect: (s) => { s.currentRun.career.reputation = 0; } },
  { id: "scouted", name: "伯樂相中", baseProb: 0.0015, text: "一位知名牧場主相中了牠，希望盡快讓牠轉入配種生涯。", reason: "伯樂相中", cond: () => true, effect: (s) => { s.currentRun.career.reputation += 30; } },
];
const RARE_ENDING_TOTAL = 0.008;

function pickWeightedEligible(items, weightFn, s, ctx) {
  const eligible = items.filter((it) => it.cond(s, ctx));
  if (eligible.length === 0) return null;
  const weighted = eligible.map((it) => ({ it, w: weightFn(it, eligible) }));
  const total = weighted.reduce((sum, x) => sum + x.w, 0);
  let r = Math.random() * total;
  for (const x of weighted) {
    r -= x.w;
    if (r <= 0) return x.it;
  }
  return weighted[weighted.length - 1].it;
}

function pickGeneralEvent(s, ctx) {
  const pool = [];
  GENERAL_CATEGORIES.forEach(({ list, totalProb }) => {
    const eligible = list.filter((ev) => ev.cond(s, ctx));
    if (eligible.length === 0) return;
    const share = totalProb / eligible.length;
    eligible.forEach((ev) => pool.push({ ev, w: share }));
  });
  if (pool.length === 0) return null;
  const total = pool.reduce((sum, x) => sum + x.w, 0);
  let r = Math.random() * total;
  for (const x of pool) {
    r -= x.w;
    if (r <= 0) return x.ev;
  }
  return pool[pool.length - 1].ev;
}

// 主要進入點：回合結束事件判定。回傳 null（無事件）或 { event, category, text, endsCareer, reason }
function resolveTurnEndEvent(state, ctx) {
  const roll = Math.random();
  if (roll < RARE_ENDING_TOTAL) {
    const ev = pickWeightedEligible(RARE_ENDING, (it) => it.baseProb, state, ctx);
    if (ev) {
      ev.effect(state, ctx);
      return { event: ev, category: "rare-ending", name: ev.name, text: ev.text, endsCareer: true, reason: ev.reason };
    }
  } else if (roll < RARE_ENDING_TOTAL + RARE_POSITIVE_TOTAL) {
    const ev = pickWeightedEligible(RARE_POSITIVE, (it) => it.baseProb, state, ctx);
    if (ev) {
      ev.effect(state, ctx);
      return { event: ev, category: "rare-positive", name: ev.name, text: ev.text, endsCareer: false };
    }
  } else if (roll < RARE_ENDING_TOTAL + RARE_POSITIVE_TOTAL + GENERAL_LAYER_TOTAL) {
    const ev = pickGeneralEvent(state, ctx);
    if (ev) {
      ev.effect(state, ctx);
      return { event: ev, category: ev.category, name: ev.name, text: ev.text, endsCareer: false };
    }
  }
  return null;
}
