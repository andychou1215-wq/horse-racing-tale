// fame-guard-smoke.js — 驗證 v0.0.9：名聲點數兌換勾選合計超出擁有點數時會阻擋並跳出提示
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

  // 進新馬生成畫面
  click('[data-action="new-game"]');

  // 讓點數(170)不足以支付三檔位合計(300)，但每個檔位單獨門檻都能通過(50/100/150)，所以三個checkbox都會是enabled
  window.gameState.meta.legacyFamePoints = 170;
  window.renderApp();

  click('[data-action="toggle-fame"][data-id="stat5"]');
  click('[data-action="toggle-fame"][data-id="aptitude1"]');
  click('[data-action="toggle-fame"][data-id="stat3each"]');

  if (window.UI.state.selectedFame.length !== 3) {
    throw new Error("三個檔位未能成功勾選: " + JSON.stringify(window.UI.state.selectedFame));
  }

  // 嘗試確認 -> 應該被擋下、跳出提示，不會開始生涯
  click('[data-action="confirm-new-horse"]');

  if (!window.UI.state.confirmDialog || !window.UI.state.confirmDialog.alertOnly) {
    throw new Error("預期跳出點數不足提示框，但未出現");
  }
  if (window.gameState.currentRun) {
    throw new Error("點數不足時生涯不應該開始，但 currentRun 已被建立");
  }
  if (window.gameState.meta.legacyFamePoints !== 170) {
    throw new Error("點數不足被擋下時，累積名聲點數不應該被扣除，目前為 " + window.gameState.meta.legacyFamePoints);
  }
  const dialogText = doc.querySelector(".confirm-box p");
  if (!dialogText || !dialogText.textContent.includes("點數超出目前擁有的點數")) {
    throw new Error("提示文字不符預期: " + (dialogText && dialogText.textContent));
  }

  // 關閉提示框
  click('[data-action="confirm-no"]');
  if (window.UI.state.confirmDialog) throw new Error("關閉提示後 confirmDialog 應為 null");

  // 取消一個檔位，讓合計(150)不超出點數(170) -> 應該可以正常開始生涯
  click('[data-action="toggle-fame"][data-id="stat3each"]');
  click('[data-action="confirm-new-horse"]');

  if (!window.gameState.currentRun) {
    throw new Error("點數足夠時應該要能正常開始生涯");
  }
  if (window.gameState.meta.legacyFamePoints !== 20) {
    throw new Error("預期扣除150點後剩20點，實際為 " + window.gameState.meta.legacyFamePoints);
  }

  console.log("名聲點數兌換阻擋機制測試通過！");
}

main().catch((err) => {
  console.error("測試失敗：", err);
  process.exit(1);
});
