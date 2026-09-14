// horseGen.js — 馬匹初始屬性生成（horse-generation.md）
"use strict";

// 第一步+第二步：品質等級 → 總點數 → 四維分配（地板15 + 隨機權重分配剩餘點數）
function generateCoreStats(qualityProbOverride) {
  const tierId = pickQualityTier(qualityProbOverride);
  const tier = tierInfo(tierId);
  const totalPoints = randInt(tier.min, tier.max);
  const stats = { speed: STAT_FLOOR, stamina: STAT_FLOOR, power: STAT_FLOOR, luck: STAT_FLOOR };
  const remain = totalPoints - STAT_FLOOR * 4;
  const weights = [Math.random(), Math.random(), Math.random(), Math.random()];
  const wSum = weights.reduce((a, b) => a + b, 0);
  const keys = ["speed", "stamina", "power", "luck"];
  let allocated = 0;
  keys.forEach((k, i) => {
    let share;
    if (i === keys.length - 1) {
      share = remain - allocated; // 剩餘誤差歸給最後一項（幸運/穩定性）
    } else {
      share = Math.round((weights[i] / wSum) * remain);
      allocated += share;
    }
    stats[k] += share;
  });
  return { tierId, tierName: tier.name, totalPoints, stats };
}

// 距離傾向軸模型：主戰位置常態分布 → 各分類差距 → 等級
function generateDistanceAptitude(meanOverride) {
  const mean = meanOverride === undefined ? 2.5 : meanOverride;
  let position = randNormal(mean, 0.7);
  position = clamp(position, 1.0, 4.0);
  const grades = {};
  DISTANCE_CAT_ORDER.forEach((catId) => {
    const diff = Math.abs(DISTANCE_CATEGORIES[catId].position - position);
    grades[catId] = gradeFromDiff(diff).grade;
  });
  return { position, grades };
}

// 跑法適性：四種各自獨立鐘形分布抽樣
function generateStyleAptitude() {
  const grades = {};
  STYLE_LIST.forEach((s) => {
    grades[s.id] = rollStyleGrade();
  });
  return grades;
}

function bestStyle(styleGrades) {
  const order = { S: 6, A: 5, B: 4, C: 3, D: 2, E: 1 };
  let best = STYLE_LIST[0].id;
  STYLE_LIST.forEach((s) => {
    if (order[styleGrades[s.id]] > order[styleGrades[best]]) best = s.id;
  });
  return best;
}

function generateHorse(name, opts) {
  opts = opts || {};
  const core = generateCoreStats(opts.qualityProbOverride);
  const dist = generateDistanceAptitude(opts.distanceMeanOverride);
  const style = generateStyleAptitude();
  return {
    name: name || "無名馬",
    qualityTier: core.tierId,
    qualityTierName: core.tierName,
    stats: core.stats,
    statCapBonus: 0, // 覺醒時刻等永久性事件加成上限
    aptitudes: {
      distanceMainPosition: dist.position,
      distanceGrades: dist.grades,
      styleGrades: style,
    },
    chosenStyle: bestStyle(style),
  };
}

function effectiveStatCap(horse) {
  return STAT_CAP_PERMANENT + (horse.statCapBonus || 0);
}

function addStatPermanent(horse, statId, amount) {
  const cap = effectiveStatCap(horse);
  horse.stats[statId] = clamp(horse.stats[statId] + amount, STAT_FLOOR, cap);
}

function distanceAptitudeBonus(horse, distanceCatId) {
  const grade = horse.aptitudes.distanceGrades[distanceCatId];
  const row = APTITUDE_GRADE_TABLE.find((r) => r.grade === grade);
  return row ? row.bonus : 0;
}

function styleAptitudeBonus(horse, styleId) {
  return styleGradeBonus(horse.aptitudes.styleGrades[styleId]);
}
