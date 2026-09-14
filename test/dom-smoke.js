// dom-smoke.js — 用 jsdom 載入 index.html，模擬點擊跑完一整輪生涯，檢查 UI 邏輯不會拋錯
"use strict";
const path = require("path");
const { JSDOM } = require("jsdom");

async function main() {
  const dom = await JSDOM.fromFile(path.join(__dirname, "..", "index.html"), {
    runScripts: "dangerously",
    resources: "usable",
  });
  const { window } = dom;

  // jsdom 在 file:// 來源下 localStorage 可能丟出例外，測試用記憶體版本取代（不影響瀏覽器實際行為）
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
  const clickAction = (action, extraMatch) => {
    const els = [...doc.querySelectorAll(`[data-action="${action}"]`)];
    const el = extraMatch ? els.find(extraMatch) : els[0];
    if (!el) throw new Error("找不到 action: " + action);
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  };

  console.log("畫面：", window.UI.state.screen);
  clickAction("new-game");
  console.log("畫面：", window.UI.state.screen);
  if (window.UI.state.screen !== "newHorse") throw new Error("應進入新馬生成畫面");

  clickAction("confirm-new-horse");
  console.log("畫面：", window.UI.state.screen);
  if (window.UI.state.screen !== "careerMain") throw new Error("應進入生涯主畫面");

  let guard = 0;
  let sawRaceAnim = false, sawEvent = false, sawRetirement = false;
  while (guard < 400) {
    guard++;
    const screen = window.UI.state.screen;
    if (screen === "retirementSummary") { sawRetirement = true; break; }
    if (screen === "careerMain") {
      const raceBtn = doc.querySelector('[data-action="go-race-preview"]');
      if (raceBtn) {
        clickAction("go-race-preview");
      } else {
        const restBtn = doc.querySelector('[data-action="do-rest"]');
        const career = window.gameState.currentRun.career;
        if (career.fatigue >= 55 && restBtn) {
          clickAction("do-rest");
        } else {
          const trainBtns = [...doc.querySelectorAll('[data-action="do-train"]')];
          if (trainBtns.length > 0) {
            const el = trainBtns[Math.floor(Math.random() * trainBtns.length)];
            el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
          } else {
            clickAction("do-rest");
          }
        }
      }
    } else if (screen === "racePreview") {
      const raceDef = window.UI.state.currentRaceDef;
      if (raceDef && raceDef.grade === "maiden" && !window.UI.state.maidenDistanceCat) {
        // 模擬玩家在新馬戰預覽畫面自選距離（v0.0.3：新馬戰距離自選）
        clickAction("select-maiden-distance");
      }
      clickAction("confirm-race");
      sawRaceAnim = true;
    } else if (screen === "raceAnim") {
      // 動畫由 setInterval 驅動（真實計時器），等待跑完
      await new Promise((r) => setTimeout(r, 3200));
    } else if (screen === "raceResult") {
      clickAction("race-continue");
    } else {
      // 事件彈窗或確認彈窗蓋在上面
      if (doc.querySelector('[data-action="dismiss-event"]')) {
        sawEvent = true;
        clickAction("dismiss-event");
      } else if (doc.querySelector('[data-action="confirm-yes"]')) {
        clickAction("confirm-yes");
      } else {
        await new Promise((r) => setTimeout(r, 50));
      }
    }
    // 處理疊加在畫面上的彈窗（即使主畫面已改變，也可能同時有 overlay）
    if (doc.querySelector('[data-action="dismiss-event"]')) {
      sawEvent = true;
      clickAction("dismiss-event");
    }
    if (doc.querySelector('[data-action="confirm-yes"]')) {
      clickAction("confirm-yes");
    }
    await new Promise((r) => setTimeout(r, 10));
  }

  console.log("最終畫面：", window.UI.state.screen, "guard:", guard);
  console.log("看過比賽動畫：", sawRaceAnim, "看過事件：", sawEvent, "看過引退結算：", sawRetirement);
  if (sawRetirement) {
    console.log("引退結算：", JSON.stringify(window.UI.state.retirementSummary));
  }
  if (!sawRetirement && guard >= 400) {
    throw new Error("400 次迭代仍未結束生涯，流程可能卡住");
  }
  console.log("DOM 煙霧測試通過！");
  window.close();
}

main().catch((e) => {
  console.error("測試失敗:", e && e.stack || e);
  process.exit(1);
});
