// gate-order-smoke.js — 驗證 v0.1.1：比賽動畫的賽道列順序固定依閘位排列，
// 不會在比賽跑到一半時因為即時名次變化而重新排列；比賽結果列表則固定依最終名次排序。
"use strict";
const path = require("path");
const { JSDOM } = require("jsdom");

async function main() {
  const dom = await JSDOM.fromFile(path.join(__dirname, "..", "index.html"), {
    runScripts: "dangerously",
    resources: "usable",
  });
  const { window } = dom;

  const memStore = {};
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (k) => (k in memStore ? memStore[k] : null),
      setItem: (k, v) => { memStore[k] = String(v); },
      removeItem: (k) => { delete memStore[k]; },
    },
    configurable: true,
  });

  await new Promise((resolve, reject) => {
    let settled = false;
    window.addEventListener("error", (e) => {
      if (!settled) { settled = true; reject(e.error || e.message); }
    });
    window.document.addEventListener("DOMContentLoaded", () => {
      setTimeout(() => { if (!settled) { settled = true; resolve(); } }, 300);
    });
  });

  const doc = window.document;
  const click = (selector) => {
    const el = doc.querySelector(selector);
    if (!el) throw new Error("找不到元素: " + selector);
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  };

  click('[data-action="new-game"]');
  click('[data-action="confirm-new-horse"]');
  if (!window.gameState.currentRun) throw new Error("生涯應該已開始");

  // 第3回合固定是新馬戰，強制出賽（不可訓練/休息）；期間可能跳出事件/確認彈窗，需先關閉再繼續
  let guard = 0;
  while (window.gameState.currentRun.career.turn < 3 && guard < 100) {
    guard++;
    if (doc.querySelector('[data-action="dismiss-event"]')) {
      click('[data-action="dismiss-event"]');
      continue;
    }
    if (doc.querySelector('[data-action="confirm-yes"]')) {
      click('[data-action="confirm-yes"]');
      continue;
    }
    if (doc.querySelector('[data-action="confirm-no"]')) {
      click('[data-action="confirm-no"]');
      continue;
    }
    const restBtn = doc.querySelector('[data-action="do-rest"]');
    if (restBtn) {
      click('[data-action="do-rest"]');
    }
  }
  if (window.gameState.currentRun.career.turn < 3) {
    throw new Error("無法推進到第3回合新馬戰，可能卡在某個畫面/彈窗");
  }
  click('[data-action="go-race-preview"]');
  click('[data-action="select-maiden-distance"][data-cat="short"]');
  click('[data-action="confirm-race"]');

  if (window.UI.state.screen !== "raceAnim") {
    throw new Error("預期進入比賽動畫畫面，實際為 " + window.UI.state.screen);
  }
  clearInterval(window.UI.state.animTimer);
  window.UI.state.animTimer = null;

  const sim = window.UI.state.lastActionResult.raceSimResult;
  const expectedLaneGateOrder = sim.entries.slice().sort((a, b) => a.gate - b.gate).map((e) => e.gate);

  const readLaneGatesFromDom = () => {
    const markers = Array.from(doc.querySelectorAll(".marker"));
    return markers.map((m) => {
      const match = m.textContent.match(/^\[(\d+)\]/);
      if (!match) throw new Error("動畫標記文字找不到閘位號碼: " + m.textContent);
      return Number(match[1]);
    });
  };

  // tick 0：檢查初始賽道列順序
  window.UI.state.animTick = 0;
  window.renderApp();
  const lanesAtStart = readLaneGatesFromDom();
  if (JSON.stringify(lanesAtStart) !== JSON.stringify(expectedLaneGateOrder)) {
    throw new Error(
      "比賽開始時賽道列順序應依閘位排列，預期 " + JSON.stringify(expectedLaneGateOrder) +
      "，實際 " + JSON.stringify(lanesAtStart)
    );
  }

  // 跑到比賽中段：賽道列順序不應該改變（即使各馬進度已經明顯拉開名次）
  const midTick = Math.floor((sim.numTicks - 1) / 2);
  window.UI.state.animTick = midTick;
  window.renderApp();
  const lanesAtMid = readLaneGatesFromDom();
  if (JSON.stringify(lanesAtMid) !== JSON.stringify(expectedLaneGateOrder)) {
    throw new Error(
      "比賽進行到一半時賽道列順序不應該改變，預期 " + JSON.stringify(expectedLaneGateOrder) +
      "，實際 " + JSON.stringify(lanesAtMid)
    );
  }

  // 跑到終點附近：賽道列順序仍不應該改變
  window.UI.state.animTick = sim.numTicks - 1;
  window.renderApp();
  const lanesAtEnd = readLaneGatesFromDom();
  if (JSON.stringify(lanesAtEnd) !== JSON.stringify(expectedLaneGateOrder)) {
    throw new Error(
      "比賽即將結束時賽道列順序仍不應該改變，預期 " + JSON.stringify(expectedLaneGateOrder) +
      "，實際 " + JSON.stringify(lanesAtEnd)
    );
  }

  // 切到結果畫面：結果列表應依最終名次排序（跟閘位順序通常不同）
  window.UI.state.screen = "raceResult";
  window.renderApp();
  const resultRows = Array.from(doc.querySelectorAll(".result-row")).map((row) => {
    const span = row.querySelector("span");
    const match = span.textContent.match(/^(\d+)\./);
    if (!match) throw new Error("結果列表文字找不到名次: " + span.textContent);
    return Number(match[1]);
  });
  const expectedPlacements = resultRows.slice().sort((a, b) => a - b);
  if (JSON.stringify(resultRows) !== JSON.stringify(expectedPlacements)) {
    throw new Error(
      "比賽結果列表應依名次由小到大排序，實際順序 " + JSON.stringify(resultRows)
    );
  }
  if (JSON.stringify(resultRows) !== JSON.stringify(Array.from({ length: resultRows.length }, (_, i) => i + 1))) {
    throw new Error("比賽結果名次應為 1..N 的完整排列，實際為 " + JSON.stringify(resultRows));
  }

  console.log("閘位排列固定賽道列順序測試通過！");
  window.close();
  process.exit(0);
}

main().catch((err) => {
  console.error("測試失敗：", err);
  process.exit(1);
});
