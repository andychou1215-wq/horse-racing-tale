// constants.js — 全域數值設定，數字皆取自專案規格文件；部分未明訂細節（標註 NOTE）為原型階段的合理預設值，之後可依實測調整。
"use strict";

const GAME_VERSION = "v0.0.6";

const STAT_CAP_PERMANENT = 160;
const STAT_CAP_TEMP = 170;
const ENERGY_CAP = 100;
const FATIGUE_CAP = 100;
const ENERGY_REGEN_PER_TURN = 15;
const STAT_FLOOR = 15;
const TOTAL_TURNS = 36;
const BASE_GROWTH = 10; // NOTE: 文件未指定基礎成長值，先用 10 作為可調參數

const QUALITY_TIERS = [
  { id: "bad", name: "不良", min: 100, max: 115, prob: 0.50 },
  { id: "normal", name: "普通", min: 116, max: 130, prob: 0.30 },
  { id: "good", name: "優良", min: 131, max: 145, prob: 0.15 },
  { id: "rare", name: "稀有", min: 146, max: 160, prob: 0.05 },
];

const DISTANCE_CATEGORIES = {
  short: { id: "short", name: "短距離", position: 1.0, enduranceCoef: 1.0 },
  mile: { id: "mile", name: "一哩", position: 2.0, enduranceCoef: 1.2 },
  middle: { id: "middle", name: "中距離", position: 3.0, enduranceCoef: 1.6 },
  long: { id: "long", name: "長距離", position: 4.0, enduranceCoef: 2.0 },
};
const DISTANCE_CAT_ORDER = ["short", "mile", "middle", "long"];

// v0.0.6：跑法適性改採「跑法傾向軸」模型（比照距離適性），position 為該跑法在光譜上的位置
const STYLE_LIST = [
  { id: "front", name: "領逃", position: 1.0 },
  { id: "pace", name: "先行", position: 2.0 },
  { id: "mid", name: "居中", position: 3.0 },
  { id: "closer", name: "後追", position: 4.0 },
];
const STYLE_ORDER = ["front", "pace", "mid", "closer"];

const APTITUDE_GRADE_TABLE = [
  { max: 0.3, grade: "S", bonus: 0.10 },
  { max: 0.8, grade: "A", bonus: 0.05 },
  { max: 1.3, grade: "B", bonus: 0.0 },
  { max: 1.8, grade: "C", bonus: -0.05 },
  { max: 2.3, grade: "D", bonus: -0.10 },
  { max: Infinity, grade: "E", bonus: -0.15 },
];

const STAGES = [
  { id: "newcomer", name: "新星期", turnStart: 1, turnEnd: 8, trainingMult: 1.2, trainingAllowed: true },
  { id: "growth", name: "成長期", turnStart: 9, turnEnd: 20, trainingMult: 1.5, trainingAllowed: true },
  { id: "peak", name: "巔峰期", turnStart: 21, turnEnd: 32, trainingMult: 0.8, trainingAllowed: true },
  { id: "retirement", name: "引退期", turnStart: 33, turnEnd: 36, trainingMult: 0, trainingAllowed: false },
];

function getStage(turn) {
  return STAGES.find((s) => turn >= s.turnStart && turn <= s.turnEnd) || STAGES[STAGES.length - 1];
}

const TRAINING_ACTIONS = {
  light: { id: "light", name: "輕度訓練", energyDelta: -15, fatigueDelta: 10, growthMult: 0.6, injuryBase: 0.01, endsCareerOnInjury: false },
  standard: { id: "standard", name: "標準訓練", energyDelta: -25, fatigueDelta: 18, growthMult: 1.0, injuryBase: 0.03, endsCareerOnInjury: false },
  intense: { id: "intense", name: "強化訓練", energyDelta: -35, fatigueDelta: 28, growthMult: 1.5, injuryBase: 0.06, extraInjury: 0.05, endsCareerOnInjury: true },
};

const REST_ACTION = { energyDelta: 35, fatigueDelta: -25 };
const RACE_ACTION_BASE = { energyDelta: -40, fatigueDelta: 30, injuryBase: 0.05 };

const FATIGUE_WARN_THRESHOLD = 80;
const FATIGUE_CRITICAL_THRESHOLD = 95;
const FATIGUE_CRITICAL_CHECK_PROB = 0.20;

// 賽事日曆：第3/6/8回合為新星期分支邏輯（於 state.js 動態判定），其餘為固定排程
// 第3回合新馬戰不在此表列出固定距離——v0.0.3起改由玩家於出賽預覽畫面自選距離（見 state.js getScheduledRace()/doRaceAction()）
const RACE_CALENDAR_FIXED = {
  10: { name: "春季公開賽", grade: "open", distanceCat: "middle", distance: 2000 },
  13: { name: "一哩錦標賽", grade: "open", distanceCat: "mile", distance: 1600 },
  16: { name: "長距離挑戰賽", grade: "open", distanceCat: "long", distance: 3000 },
  19: { name: "成長盃總決賽", grade: "open", distanceCat: "middle", distance: 2400 },
  22: { name: "G3短距離賽", grade: "G3", distanceCat: "short", distance: 1200 },
  24: { name: "G3一哩賽", grade: "G3", distanceCat: "mile", distance: 1600 },
  26: { name: "G2中距離賽", grade: "G2", distanceCat: "middle", distance: 2000 },
  28: { name: "G2長距離賽", grade: "G2", distanceCat: "long", distance: 3000 },
  30: { name: "G1一哩經典賽", grade: "G1", distanceCat: "mile", distance: 1600 },
  32: { name: "G1長距離大賞", grade: "G1", distanceCat: "long", distance: 3000 },
  34: { name: "引退紀念賽", grade: "retirementRace", distanceCat: null, distance: null },
};
const NON_WINNER_TURNS = [6, 8];

const GRADE_INFO = {
  maiden: { name: "新馬賽", basePrize: 500, baseRep: 5, baseScore: 10, fieldSize: 6, timeCoef: 1.08, aiQuality: [0.50, 0.30, 0.15, 0.05] },
  nonWinner: { name: "未勝利賽", basePrize: 400, baseRep: 4, baseScore: 8, fieldSize: 6, timeCoef: 1.08, aiQuality: [0.50, 0.30, 0.15, 0.05] },
  open: { name: "公開賽", basePrize: 900, baseRep: 7.5, baseScore: 20, fieldSize: 7, timeCoef: 1.05, aiQuality: [0.30, 0.40, 0.22, 0.08] },
  G3: { name: "G3", basePrize: 1500, baseRep: 12.5, baseScore: 40, fieldSize: 7, timeCoef: 1.03, aiQuality: [0.15, 0.35, 0.35, 0.15] },
  G2: { name: "G2", basePrize: 2500, baseRep: 20, baseScore: 70, fieldSize: 8, timeCoef: 1.015, aiQuality: [0.05, 0.25, 0.45, 0.25] },
  G1: { name: "G1", basePrize: 4000, baseRep: 30, baseScore: 120, fieldSize: 8, timeCoef: 1.00, aiQuality: [0.00, 0.10, 0.50, 0.40] },
  retirementRace: { name: "引退紀念賽", basePrize: 2000, baseRep: 15, baseScore: 60, fieldSize: 8, timeCoef: 1.01, aiQuality: [0.05, 0.25, 0.45, 0.25] },
};

const PLACEMENT_PAYOUT = [1.0, 0.4, 0.2, 0.1, 0, 0, 0, 0];
const APPEARANCE_FEE_RATE = 0.05;

const BASE_FINISH_TIME = { 1200: 66.7, 1600: 92.0, 2000: 117.9, 2400: 143.5, 3000: 184.3 };
const TIME_CONVERSION_COEF = { 1200: 0.028, 1600: 0.032, 2000: 0.040, 2400: 0.045, 3000: 0.055 }; // NOTE: 文件未給定數值，原型階段自訂

const FAME_EXCHANGE_TIERS = [
  { threshold: 50, id: "stat5", desc: "總屬性點數額外 +5" },
  { threshold: 100, id: "aptitude1", desc: "任選一項適性等級提升一級" },
  { threshold: 150, id: "stat3each", desc: "四項核心屬性各直接 +3" },
];

const RETIREMENT_COMPLETENESS = {
  normal: 1.0, 伯樂相中: 1.0, 重大傷病: 0.7, 醜聞風波: 0.7, 天災意外: 0.7, 疲勞累積: 0.7,
};
const RETIREMENT_REASON_LABEL = {
  normal: "順利跑完全程", 伯樂相中: "伯樂相中，轉入配種生涯", 重大傷病: "重大傷病",
  醜聞風波: "醜聞風波", 天災意外: "天災意外", 疲勞累積: "疲勞累積成傷",
};

const TITLE_TABLE = [
  { min: 1000, title: "傳奇名馬" },
  { min: 700, title: "巔峰王者" },
  { min: 450, title: "頭號熱門" },
  { min: 250, title: "常勝大師" },
  { min: 100, title: "一代強者" },
  { min: 0, title: "平凡之輩" },
];

const SAVE_KEY = "horseRacingTale_save_v1";
