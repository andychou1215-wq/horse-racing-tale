// state.js — 存讀檔與生涯流程編排（data-structure.md + game-loop.md）
"use strict";

function newMeta() {
  return {
    legacyFamePoints: 0,
    totalRunsCompleted: 0,
    bestCareerScore: 0,
    bestTitle: null,
    personalBestTimes: { 1200: null, 1600: null, 2000: null, 2400: null, 3000: null },
    runHistory: [],
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return { version: 1, meta: newMeta(), currentRun: null };
    const parsed = JSON.parse(raw);
    if (!parsed.meta) parsed.meta = newMeta();
    return parsed;
  } catch (e) {
    console.warn("讀取存檔失敗，使用新存檔", e);
    return { version: 1, meta: newMeta(), currentRun: null };
  }
}

function saveState(state) {
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn("存檔失敗", e);
  }
}

function newCareer() {
  return {
    turn: 1,
    stage: "newcomer",
    energy: 100,
    fatigue: 0,
    money: 0,
    reputation: 0,
    maidenWon: null,
    nonWinnerAttempts: 0,
    openRaceUnlocked: false,
    trainingStreak: { stat: null, count: 0 },
    activeBuffs: [],
    raceHistory: [],
    eventLog: [],
    isRetired: false,
    retirementReason: null,
    firstTrainingDone: false,
    injuryRiskBonusNextTurn: 0,
    talentBuff: null,
  };
}

function startNewRun(state, horseNameOrObject, fameExchangeIds) {
  const horse = typeof horseNameOrObject === "object" && horseNameOrObject !== null
    ? horseNameOrObject
    : generateHorse(horseNameOrObject || "無名馬");
  fameExchangeIds = fameExchangeIds || [];
  if (fameExchangeIds.includes("stat5")) {
    const keys = ["speed", "stamina", "power", "luck"];
    const weights = keys.map(() => Math.random());
    const wSum = weights.reduce((a, b) => a + b, 0);
    keys.forEach((k, i) => addStatPermanent(horse, k, Math.round((weights[i] / wSum) * 5)));
  }
  if (fameExchangeIds.includes("aptitude1")) {
    // 任選一項適性等級提升一級：原型階段自動挑選主戰位置微調，讓其中一個距離分類上升一級
    horse.aptitudes.distanceMainPosition = clamp(horse.aptitudes.distanceMainPosition + 0.55, 1.0, 4.0);
    DISTANCE_CAT_ORDER.forEach((catId) => {
      const diff = Math.abs(DISTANCE_CATEGORIES[catId].position - horse.aptitudes.distanceMainPosition);
      horse.aptitudes.distanceGrades[catId] = gradeFromDiff(diff).grade;
    });
  }
  if (fameExchangeIds.includes("stat3each")) {
    ["speed", "stamina", "power", "luck"].forEach((k) => addStatPermanent(horse, k, 3));
  }
  state.currentRun = { horse, career: newCareer() };
  saveState(state);
  return state.currentRun;
}

function popInjuryRiskBonus(career) {
  const b = career.injuryRiskBonusNextTurn || 0;
  career.injuryRiskBonusNextTurn = 0;
  return b;
}

function getScheduledRace(state) {
  const career = state.currentRun.career;
  const turn = career.turn;
  if (turn === 3) return { name: "新馬戰", grade: "maiden", distanceCat: "short", distance: 1200 };
  if (NON_WINNER_TURNS.includes(turn)) {
    if (!career.maidenWon) {
      return { name: `未勝利賽`, grade: "nonWinner", distanceCat: "mile", distance: 1600 };
    }
    return null;
  }
  if (turn === 34) return { name: "引退紀念賽", grade: "retirementRace", distanceCat: null, distance: null };
  const fixed = RACE_CALENDAR_FIXED[turn];
  if (fixed) return { ...fixed };
  return null;
}

function finishTurn(state, ctx) {
  const career = state.currentRun.career;
  let ended = false, reason = null, eventResult = null;

  if (ctx.injuredEndsCareer) { ended = true; reason = "疲勞累積"; }

  if (!ended && career.fatigue >= FATIGUE_CRITICAL_THRESHOLD) {
    if (Math.random() < FATIGUE_CRITICAL_CHECK_PROB) { ended = true; reason = "疲勞累積"; }
  }

  if (!ended) {
    eventResult = resolveTurnEndEvent(state, ctx);
    if (eventResult) {
      career.eventLog.push({ turn: career.turn, eventName: eventResult.name, category: eventResult.category });
      if (eventResult.endsCareer) { ended = true; reason = eventResult.reason; }
    }
  }

  pruneBuffs(career, career.turn);

  if (ended) {
    career.isRetired = true;
    career.retirementReason = reason;
    return { ctx, eventResult, ended: true, reason, turnOfAction: career.turn };
  }

  const turnOfAction = career.turn;
  career.turn += 1;
  if (career.turn >= TOTAL_TURNS) {
    career.turn = TOTAL_TURNS;
    career.isRetired = true;
    career.retirementReason = "normal";
    return { ctx, eventResult, ended: true, reason: "normal", turnOfAction };
  }
  career.energy = clamp(career.energy + ENERGY_REGEN_PER_TURN, 0, ENERGY_CAP);
  career.stage = getStage(career.turn).id;
  return { ctx, eventResult, ended: false, turnOfAction };
}

function doTrainingAction(state, intensity, stat) {
  const career = state.currentRun.career;
  const bonus = popInjuryRiskBonus(career);
  const ctx = applyTraining(state, intensity, stat);
  if (!ctx.injuredEndsCareer && Math.random() < bonus) ctx.injuredEndsCareer = true;
  const result = finishTurn(state, ctx);
  saveState(state);
  return result;
}

function doRestAction(state) {
  const career = state.currentRun.career;
  popInjuryRiskBonus(career);
  const ctx = applyRest(state);
  const result = finishTurn(state, ctx);
  saveState(state);
  return result;
}

const RETIREMENT_DISTANCE_MAP = { short: 1200, mile: 1600, middle: 2000, long: 3000 };

function doRaceAction(state, raceDefIn, retirementDistanceCat) {
  const career = state.currentRun.career;
  const horse = state.currentRun.horse;
  const bonus = popInjuryRiskBonus(career);

  let def = raceDefIn;
  if (def.grade === "retirementRace") {
    const catId = retirementDistanceCat || "mile";
    def = { ...def, distanceCat: catId, distance: RETIREMENT_DISTANCE_MAP[catId] };
  }
  const turnOfRace = career.turn;
  const enduranceCoef = DISTANCE_CATEGORIES[def.distanceCat].enduranceCoef;
  career.energy = clamp(career.energy + RACE_ACTION_BASE.energyDelta * enduranceCoef, 0, ENERGY_CAP);
  career.fatigue = clamp(career.fatigue + RACE_ACTION_BASE.fatigueDelta * enduranceCoef, 0, FATIGUE_CAP);

  const aiHorses = generateAIField(def.grade, def.distanceCat);
  const simResult = simulateRace(def, horse, career, aiHorses);
  const rawPlacement = simResult.playerEntry.placement;
  const fieldSize = simResult.entries.length;

  // 與訓練同一套原則：受傷觸發造成額外疲勞衝擊，由疲勞≥95 的累積型判定機制決定是否強制引退
  let injuryProb = computeInjuryProb(RACE_ACTION_BASE.injuryBase, career.fatigue, false);
  let injured = Math.random() < injuryProb || Math.random() < bonus;
  if (injured) career.fatigue = clamp(career.fatigue + 15, 0, FATIGUE_CAP);

  const raceCtxData = { grade: def.grade, placement: rawPlacement, fieldSize, distance: def.distance, distanceCat: def.distanceCat, mistakeApplied: false, doublePrize: false };
  const ctx = { type: "race", stage: getStage(career.turn).id, race: raceCtxData, injuredEndsCareer: false, injured, injuryProb };

  const turnResult = finishTurn(state, ctx);

  const finalPlacement = clamp(rawPlacement + (raceCtxData.mistakeApplied ? 1 : 0), 1, fieldSize);
  const payout = computeRacePayout(finalPlacement, def.grade);
  let prize = payout.prize;
  if (raceCtxData.doublePrize) prize *= 2;

  career.money += prize;
  career.reputation += payout.rep;

  if (def.grade === "maiden") {
    career.maidenWon = finalPlacement === 1;
    if (career.maidenWon) career.openRaceUnlocked = true;
  } else if (def.grade === "nonWinner") {
    career.nonWinnerAttempts = (career.nonWinnerAttempts || 0) + 1;
    if (finalPlacement === 1) { career.maidenWon = true; career.openRaceUnlocked = true; }
  }
  if (turnOfRace >= 10) career.openRaceUnlocked = true;

  career.raceHistory.push({
    turn: turnOfRace, raceName: def.name, grade: def.grade, distance: def.distance,
    placement: finalPlacement, time: Math.round(simResult.playerEntry.time * 10) / 10,
    prizeEarned: Math.round(prize), reputationEarned: Math.round(payout.rep * 10) / 10,
  });

  saveState(state);
  return { ...turnResult, raceSimResult: simResult, finalPlacement, prize, rep: payout.rep, raceDef: def };
}

function finalizeRunAndGetSummary(state) {
  const summary = computeRetirementSummary(state);
  applyRetirementToMeta(state, summary);
  state.currentRun = null;
  saveState(state);
  return summary;
}
