// utils.js — 共用小工具
"use strict";

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function randFloat(min, max) {
  return Math.random() * (max - min) + min;
}

// Box-Muller 常態分布抽樣
function randNormal(mean, sd) {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  return mean + z * sd;
}

// 依權重物件陣列（含 prob/weight 欄位）做加權隨機抽取，weightKey 指定使用的欄位名
function weightedPick(items, weightKey) {
  const total = items.reduce((s, it) => s + (it[weightKey] || 0), 0);
  if (total <= 0) return null;
  let r = Math.random() * total;
  for (const it of items) {
    r -= it[weightKey] || 0;
    if (r <= 0) return it;
  }
  return items[items.length - 1];
}

function pickQualityTier(probOverride) {
  const table = probOverride || QUALITY_TIERS.map((t) => ({ id: t.id, prob: t.prob }));
  let r = Math.random();
  let acc = 0;
  for (const t of table) {
    acc += t.prob;
    if (r <= acc) return t.id;
  }
  return table[table.length - 1].id;
}

function tierInfo(id) {
  return QUALITY_TIERS.find((t) => t.id === id);
}

function gradeFromDiff(diff) {
  for (const row of APTITUDE_GRADE_TABLE) {
    if (diff <= row.max) return row;
  }
  return APTITUDE_GRADE_TABLE[APTITUDE_GRADE_TABLE.length - 1];
}

function rollStyleGrade() {
  const r = weightedPick(STYLE_GRADE_PROB, "prob");
  return r.grade;
}

function styleGradeBonus(grade) {
  const row = STYLE_GRADE_PROB.find((g) => g.grade === grade);
  return row ? row.bonus : 0;
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(1);
  return `${m}:${s.padStart(4, "0")}`;
}

function fmtNum(n) {
  return Math.round(n).toLocaleString("zh-TW");
}

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function statLabel(id) {
  return { speed: "速度", stamina: "耐力", power: "爆發力", luck: "幸運/穩定性" }[id] || id;
}

function distanceCatLabel(id) {
  return DISTANCE_CATEGORIES[id] ? DISTANCE_CATEGORIES[id].name : id;
}

function styleLabel(id) {
  const s = STYLE_LIST.find((x) => x.id === id);
  return s ? s.name : id;
}
