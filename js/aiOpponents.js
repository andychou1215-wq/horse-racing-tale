// aiOpponents.js — AI對手生成規則（ai-opponents.md）
"use strict";

function generateAIHorse(index, grade, distanceCatId) {
  const gradeInfo = GRADE_INFO[grade];
  const qualityProbOverride = ["bad", "normal", "good", "rare"].map((id, i) => ({ id, prob: gradeInfo.aiQuality[i] }));
  const meanOverride = distanceCatId ? DISTANCE_CATEGORIES[distanceCatId].position : 2.5;
  const horse = generateHorse(`NPC${index + 1}`, { qualityProbOverride, distanceMeanOverride: meanOverride });
  horse.isAI = true;
  return horse;
}

// 保底均衡分配跑法：出賽馬數(不含玩家)≥4 時四種跑法各至少一匹，其餘依自身跑法適性最高類別分配
function assignAIStyles(aiHorses) {
  const styleOrder = { S: 6, A: 5, B: 4, C: 3, D: 2, E: 1 };
  const styles = STYLE_LIST.map((s) => s.id);
  const assigned = new Array(aiHorses.length).fill(null);
  if (aiHorses.length >= 4) {
    const pool = aiHorses.map((h, i) => ({ i, h }));
    styles.forEach((styleId) => {
      // 從尚未分配的馬中，挑出該跑法適性最高者優先保底
      let bestIdx = -1, bestVal = -1;
      pool.forEach(({ i, h }) => {
        if (assigned[i] !== null) return;
        const val = styleOrder[h.aptitudes.styleGrades[styleId]];
        if (val > bestVal) { bestVal = val; bestIdx = i; }
      });
      if (bestIdx >= 0) assigned[bestIdx] = styleId;
    });
  }
  aiHorses.forEach((h, i) => {
    if (assigned[i] === null) {
      assigned[i] = bestStyle(h.aptitudes.styleGrades);
    }
    h.chosenStyle = assigned[i];
  });
  return aiHorses;
}

function generateAIField(grade, distanceCatId) {
  const gradeInfo = GRADE_INFO[grade];
  const aiCount = gradeInfo.fieldSize - 1;
  const aiHorses = [];
  for (let i = 0; i < aiCount; i++) {
    aiHorses.push(generateAIHorse(i, grade, distanceCatId));
  }
  assignAIStyles(aiHorses);
  return aiHorses;
}
