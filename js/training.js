// training.js — 訓練/體力消耗數值公式（training-mechanics.md）
"use strict";

function computeInjuryProb(baseProb, fatigue, isIntense) {
  let p = baseProb + (fatigue / 50) * 0.10;
  if (isIntense) p += 0.05;
  return clamp(p, 0, 0.95);
}

function computeGrowth(horse, statId, growthMult, stageMult) {
  const cap = effectiveStatCap(horse);
  const current = horse.stats[statId];
  const base = BASE_GROWTH * growthMult * stageMult * (1 - current / cap);
  const flutter = randFloat(-2, 2);
  return Math.max(0, base + flutter);
}

// 回傳 ctx，供事件系統與 UI 使用
function applyTraining(state, intensityId, statId) {
  const horse = state.currentRun.horse;
  const career = state.currentRun.career;
  const action = TRAINING_ACTIONS[intensityId];
  const stage = getStage(career.turn);

  career.energy = clamp(career.energy + action.energyDelta, 0, ENERGY_CAP);
  career.fatigue = clamp(career.fatigue + action.fatigueDelta, 0, FATIGUE_CAP);

  const growth = computeGrowth(horse, statId, action.growthMult, stage.trainingMult);
  // 天賦異稟事件的持續加成
  let bonusGrowth = 0;
  if (career.talentBuff && career.talentBuff.expiresAtTurn >= career.turn && career.talentBuff.stat === statId) {
    bonusGrowth = career.talentBuff.amount;
  }
  const totalGrowth = growth + bonusGrowth;
  addStatPermanent(horse, statId, totalGrowth);

  // 訓練連續紀錄
  if (career.trainingStreak.stat === statId) {
    career.trainingStreak.count += 1;
  } else {
    career.trainingStreak = { stat: statId, count: 1 };
  }

  const isFirstTraining = !career.firstTrainingDone;
  career.firstTrainingDone = true;

  // 受傷機率：觸發時不直接結束生涯，而是造成額外疲勞衝擊，
  // 讓「連續高風險訓練 → 疲勞衝上臨界值 → 累積型強制引退判定」的因果鏈自然成立
  // （累積型提前結束的唯一硬性觸發點在 game-loop.md／training-mechanics.md 中明訂為「疲勞≥95」的判定）
  const injuryProb = computeInjuryProb(action.injuryBase, career.fatigue, intensityId === "intense");
  const injured = Math.random() < injuryProb;
  if (injured) {
    career.fatigue = clamp(career.fatigue + 15, 0, FATIGUE_CAP);
  }

  return {
    type: "training",
    intensity: intensityId,
    stat: statId,
    growthApplied: totalGrowth,
    isFirstTraining,
    stage: stage.id,
    injured,
    injuryProb,
    injuredEndsCareer: false,
  };
}

function applyRest(state) {
  const career = state.currentRun.career;
  career.energy = clamp(career.energy + REST_ACTION.energyDelta, 0, ENERGY_CAP);
  career.fatigue = clamp(career.fatigue + REST_ACTION.fatigueDelta, 0, FATIGUE_CAP);
  career.trainingStreak = { stat: null, count: 0 };
  return { type: "rest", stage: getStage(career.turn).id };
}
