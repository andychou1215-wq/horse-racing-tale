// smoke.js — 自動跑多輪生涯，檢查核心邏輯不會拋錯、數值落在合理範圍
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const files = ["constants.js", "utils.js", "horseGen.js", "aiOpponents.js", "training.js", "raceSim.js", "events.js", "retirement.js", "state.js"];
const combined = files.map((f) => fs.readFileSync(path.join(__dirname, "..", "js", f), "utf8")).join("\n;\n");

const TEST_SCRIPT = `
let stats = { runs: 0, endings: {}, titles: {}, errors: 0, minScore: Infinity, maxScore: -Infinity, turns: [] };

for (let run = 0; run < 300; run++) {
  try {
    let state = loadState();
    startNewRun(state, "測試馬" + run, []);
    let guard = 0;
    while (state.currentRun && guard < 200) {
      guard++;
      const career = state.currentRun.career;
      const scheduled = getScheduledRace(state);
      let result;
      if (scheduled && Math.random() < 0.6) {
        result = doRaceAction(state, scheduled, ["short", "mile", "middle", "long"][randInt(0, 3)]);
      } else {
        const stage = getStage(career.turn);
        if (stage.trainingAllowed && Math.random() < 0.7) {
          const intensity = ["light", "standard", "intense"][randInt(0, 2)];
          const stat = ["speed", "stamina", "power", "luck"][randInt(0, 3)];
          result = doTrainingAction(state, intensity, stat);
        } else {
          result = doRestAction(state);
        }
      }
      if (result.ended) {
        const summary = finalizeRunAndGetSummary(state);
        stats.endings[career.retirementReason] = (stats.endings[career.retirementReason] || 0) + 1;
        stats.titles[summary.title] = (stats.titles[summary.title] || 0) + 1;
        stats.minScore = Math.min(stats.minScore, summary.total);
        stats.maxScore = Math.max(stats.maxScore, summary.total);
        stats.turns.push(career.turn);
        break;
      }
    }
    stats.runs++;
  } catch (e) {
    stats.errors++;
    console.error("Run " + run + " 發生錯誤:", e.stack);
    if (stats.errors > 5) break;
  }
}
console.log(JSON.stringify(stats, null, 2));
console.log("平均結束回合:", (stats.turns.reduce((a, b) => a + b, 0) / stats.turns.length).toFixed(1));
`;

const sandbox = {
  console,
  Math,
  JSON,
  Date,
  localStorage: (() => {
    let store = {};
    return {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    };
  })(),
};
vm.createContext(sandbox);
vm.runInContext(combined + "\n" + TEST_SCRIPT, sandbox, { filename: "smoke-bundle.js" });
