// raceSim.js — 比賽模擬機制（race-simulation.md）
// 採 tick 制模擬（20 ticks），phase 依短~中距離 0-20% / 20-70% / 70-100%，長距離改為 0-15% / 15-75% / 75-100%
"use strict";

const NUM_TICKS = 20;

// 跑法風格於各階段的「推進係數」與「疲勞累積係數」（依 race-simulation.md 的敘述量化，原型可調參數）
const STYLE_PHASE_POWER = {
  front: { start: 1.30, mid: 1.00, final: 0.85 },
  pace: { start: 1.10, mid: 1.00, final: 1.05 },
  mid: { start: 0.85, mid: 1.00, final: 1.20 },
  closer: { start: 0.70, mid: 1.00, final: 1.35 },
};
const STYLE_PHASE_FATIGUE = {
  front: { start: 1.10, mid: 1.30, final: 1.00 },
  pace: { start: 1.00, mid: 1.00, final: 1.00 },
  mid: { start: 0.80, mid: 0.70, final: 1.00 },
  closer: { start: 0.70, mid: 0.60, final: 1.00 },
};

function phaseBoundaries(distanceCatId) {
  if (distanceCatId === "long") return { startEnd: 0.15, midEnd: 0.75 };
  return { startEnd: 0.20, midEnd: 0.70 };
}

function phaseAt(tickIdx, numTicks, bounds) {
  const pct = (tickIdx + 1) / numTicks;
  if (pct <= bounds.startEnd) return "start";
  if (pct <= bounds.midEnd) return "mid";
  return "final";
}

// 套用 nextRaceOnly 暫時 buff 到參賽用的統計快照（不影響永久屬性）
function buildRaceStatSnapshot(horse, career) {
  const snap = { speed: horse.stats.speed, stamina: horse.stats.stamina, power: horse.stats.power, luck: horse.stats.luck, enduranceMult: 1.0 };
  if (career && career.activeBuffs) {
    career.activeBuffs.forEach((b) => {
      if (b.scope !== "nextRaceOnly") return;
      if (b.target === "enduranceCoef") {
        snap.enduranceMult *= b.amount;
      } else if (snap[b.target] !== undefined) {
        snap[b.target] = clamp(snap[b.target] + b.amount, 0, STAT_CAP_TEMP);
      }
    });
  }
  return snap;
}

function consumeNextRaceBuffs(career) {
  if (!career.activeBuffs) return;
  career.activeBuffs = career.activeBuffs.filter((b) => b.scope !== "nextRaceOnly");
}

function simulateOneHorse(horse, statSnap, distanceCatId, enduranceCoef, numTicks, bounds) {
  const style = horse.chosenStyle;
  const powerTable = STYLE_PHASE_POWER[style];
  const fatigueTable = STYLE_PHASE_FATIGUE[style];
  const distBonus = 1 + distanceAptitudeBonus(horse, distanceCatId);
  const styleBonus = 1 + styleAptitudeBonus(horse, style);
  const staminaFactor = statSnap.stamina / 160;
  const fatigueThreshold = 50 + staminaFactor * 50; // 耐力越高，門檻觸發越晚
  const luckFactor = statSnap.luck / 160;
  const randomRange = clamp(0.30 - luckFactor * 0.22, 0.04, 0.30);

  let progress = 0;
  let raceFatigue = 0;
  const perTickBase = 100 / numTicks;
  const log = [];

  for (let t = 0; t < numTicks; t++) {
    const phase = phaseAt(t, numTicks, bounds);
    let inc = perTickBase * (1 + (statSnap.speed - 100) / 300) * powerTable[phase] * distBonus * styleBonus;
    if (raceFatigue > fatigueThreshold) inc *= 0.85; // 後繼無力
    if (phase === "final") {
      inc += perTickBase * 0.40 * ((statSnap.power - 100) / 300) * powerTable.final;
    }
    inc += perTickBase * randomRange * (Math.random() * 2 - 1);
    inc = Math.max(inc, perTickBase * 0.15);
    progress += inc;

    raceFatigue += 3 * enduranceCoef * statSnap.enduranceMult * fatigueTable[phase] - staminaFactor * 1;
    raceFatigue = Math.max(0, raceFatigue);

    log.push(progress);
  }
  return { finalScore: progress, log };
}

function simulateRace(raceDef, playerHorse, career, aiHorses) {
  const distanceCatId = raceDef.distanceCat;
  const enduranceCoef = DISTANCE_CATEGORIES[distanceCatId].enduranceCoef;
  const bounds = phaseBoundaries(distanceCatId);

  const playerSnap = buildRaceStatSnapshot(playerHorse, career);
  const entries = [{ id: "player", name: playerHorse.name, isPlayer: true, horse: playerHorse, snap: playerSnap }];
  aiHorses.forEach((h, i) => entries.push({ id: `ai${i}`, name: h.name, isPlayer: false, horse: h, snap: buildRaceStatSnapshot(h, null) }));

  entries.forEach((e) => {
    const res = simulateOneHorse(e.horse, e.snap, distanceCatId, enduranceCoef, NUM_TICKS, bounds);
    e.finalScore = res.finalScore;
    e.log = res.log;
  });

  const avgScore = entries.reduce((s, e) => s + e.finalScore, 0) / entries.length;
  const gradeInfo = GRADE_INFO[raceDef.grade];
  const baseTime = BASE_FINISH_TIME[raceDef.distance] || BASE_FINISH_TIME[1600];
  const timeCoef = gradeInfo.timeCoef;
  const conv = TIME_CONVERSION_COEF[raceDef.distance] || 0.035;

  entries.sort((a, b) => b.finalScore - a.finalScore);
  entries.forEach((e, idx) => {
    e.placement = idx + 1;
    const t = baseTime * timeCoef - (e.finalScore - avgScore) * conv;
    e.time = Math.max(t, baseTime * 0.85);
  });

  consumeNextRaceBuffs(career);

  return {
    raceDef,
    numTicks: NUM_TICKS,
    entries,
    playerEntry: entries.find((e) => e.isPlayer),
  };
}

function computeRacePayout(placement, grade) {
  const gradeInfo = GRADE_INFO[grade];
  const ratio = PLACEMENT_PAYOUT[placement - 1] || 0;
  const prize = gradeInfo.basePrize * ratio + gradeInfo.basePrize * APPEARANCE_FEE_RATE;
  const rep = gradeInfo.baseRep * ratio;
  return { prize, rep, ratio };
}
