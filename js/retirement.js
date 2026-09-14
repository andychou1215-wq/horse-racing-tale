// retirement.js — 引退結算／生涯總評計算（retirement-summary.md）
"use strict";

function computeRetirementSummary(state) {
  const run = state.currentRun;
  const horse = run.horse;
  const career = run.career;

  const raceScore = career.raceHistory.reduce((sum, r) => {
    const gradeInfo = GRADE_INFO[r.grade];
    const ratio = PLACEMENT_PAYOUT[r.placement - 1] || 0;
    return sum + gradeInfo.baseScore * ratio;
  }, 0);

  const repScore = career.reputation;
  const statScore = (horse.stats.speed + horse.stats.stamina + horse.stats.power + horse.stats.luck) * 0.5;

  const rareEventCount = career.eventLog.filter((e) => e.category === "rare-positive").length;
  const g1Wins = career.raceHistory.filter((r) => r.grade === "G1" && r.placement === 1).length;
  const specialScore = rareEventCount * 20 + g1Wins * 50;

  const completeness = RETIREMENT_COMPLETENESS[career.retirementReason] !== undefined ? RETIREMENT_COMPLETENESS[career.retirementReason] : 0.7;
  const total = (raceScore + repScore + statScore + specialScore) * completeness;

  const titleRow = TITLE_TABLE.find((t) => total >= t.min) || TITLE_TABLE[TITLE_TABLE.length - 1];

  return {
    raceScore, repScore, statScore, specialScore, completeness,
    total: Math.round(total * 10) / 10,
    title: titleRow.title,
    rareEventCount, g1Wins,
    famePointsEarned: Math.round(career.reputation),
  };
}

function applyRetirementToMeta(state, summary) {
  const meta = state.meta;
  meta.legacyFamePoints += summary.famePointsEarned;
  meta.totalRunsCompleted += 1;
  if (summary.total > meta.bestCareerScore) {
    meta.bestCareerScore = summary.total;
    meta.bestTitle = summary.title;
  }
  const career = state.currentRun.career;
  career.raceHistory.forEach((r) => {
    const best = meta.personalBestTimes[r.distance];
    if (r.time && (best === null || best === undefined || r.time < best)) {
      meta.personalBestTimes[r.distance] = r.time;
    }
  });
  meta.runHistory.unshift({
    horseName: state.currentRun.horse.name,
    title: summary.title,
    score: summary.total,
    completedAt: new Date().toISOString(),
  });
  if (meta.runHistory.length > 20) meta.runHistory.length = 20;
}
