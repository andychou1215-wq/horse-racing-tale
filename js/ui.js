// ui.js — 畫面渲染（ui-flow.md：標題／新馬生成／生涯主畫面／比賽畫面／事件彈窗／引退結算／二次確認）
"use strict";

window.UI = {
  state: {
    screen: "title",
    previewHorse: null,
    selectedFame: [],
    confirmDialog: null,
    eventToShow: null,
    pendingAfterEvent: null,
    currentRaceDef: null,
    retireDistanceCat: "mile",
    maidenDistanceCat: null,
    lastActionResult: null,
    animTick: 0,
    animTimer: null,
    retirementSummary: null,
  },
};

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function tierBadge(tierId, tierName) {
  return `<span class="badge tier-${tierId}">${tierName}</span>`;
}
function gradeBadge(grade) {
  return `<span class="badge grade-${grade}">${grade}</span>`;
}

function renderApp() {
  const root = document.getElementById("app");
  let html = "";
  switch (UI.state.screen) {
    case "title": html = renderTitleScreen(); break;
    case "newHorse": html = renderNewHorseScreen(); break;
    case "careerMain": html = renderCareerMain(); break;
    case "racePreview": html = renderRacePreview(); break;
    case "raceAnim": html = renderRaceAnim(); break;
    case "raceResult": html = renderRaceResult(); break;
    case "retirementSummary": html = renderRetirementSummary(); break;
    default: html = "<p>未知畫面</p>";
  }
  root.innerHTML = html;
  renderOverlays();
}

function renderOverlays() {
  const overlayRoot = document.getElementById("overlay-root");
  let html = "";
  if (UI.state.eventToShow) html += renderEventModal(UI.state.eventToShow);
  if (UI.state.confirmDialog) html += renderConfirmDialog(UI.state.confirmDialog);
  overlayRoot.innerHTML = html;
}

// ---------- 標題畫面 ----------
function renderTitleScreen() {
  const meta = gameState.meta;
  const hasRun = !!gameState.currentRun;
  let historyRows = "";
  if (meta.runHistory.length > 0) {
    historyRows = meta.runHistory.slice(0, 8).map((r) => `
      <tr><td>${escapeHtml(r.horseName)}</td><td>${r.title}</td><td>${Math.round(r.score)}</td></tr>
    `).join("");
  }
  return `
    <div class="title-hero">
      <h1>賽馬物語</h1>
      <p class="muted">Horse Racing Tale ${GAME_VERSION}</p>
    </div>
    <div class="panel center">
      ${hasRun ? `<button class="btn block" data-action="continue-game">繼續生涯（第 ${gameState.currentRun.career.turn} / ${TOTAL_TURNS} 回合）</button>` : ""}
      <button class="btn block secondary" data-action="new-game">開始新生涯</button>
    </div>
    <div class="panel">
      <h2>名譽紀錄</h2>
      <p>累積名聲點數：<b>${fmtNum(meta.legacyFamePoints)}</b></p>
      <p class="muted">已完成生涯 ${meta.totalRunsCompleted} 次｜最佳總評：${meta.bestCareerScore ? Math.round(meta.bestCareerScore) + "（" + meta.bestTitle + "）" : "—"}</p>
      ${historyRows ? `<table class="history"><tr><th>馬名</th><th>稱號</th><th>總評</th></tr>${historyRows}</table>` : `<p class="muted">尚無生涯紀錄</p>`}
    </div>
  `;
}

// ---------- 新馬生成畫面 ----------
function renderAptitudeGrid(grades, selectableKey) {
  return `<div class="aptitude-grid">${DISTANCE_CAT_ORDER.map((catId) => `
    <div class="aptitude-cell"><div>${distanceCatLabel(catId)}</div><div class="badge grade-${grades[catId]}">${grades[catId]}</div></div>
  `).join("")}</div>`;
}
function renderStyleGrid(horse) {
  return `<div class="aptitude-grid">${STYLE_LIST.map((s) => `
    <div class="aptitude-cell ${horse.chosenStyle === s.id ? "selected" : ""}" data-action="select-style" data-style="${s.id}">
      <div>${s.name}</div><div class="badge grade-${horse.aptitudes.styleGrades[s.id]}">${horse.aptitudes.styleGrades[s.id]}</div>
    </div>`).join("")}</div>`;
}

function renderNewHorseScreen() {
  if (!UI.state.previewHorse) UI.state.previewHorse = generateHorse("新星");
  const h = UI.state.previewHorse;
  const meta = gameState.meta;
  const fameOptions = FAME_EXCHANGE_TIERS.map((t) => {
    const enabled = meta.legacyFamePoints >= t.threshold;
    const checked = UI.state.selectedFame.includes(t.id);
    return `<label class="row" style="opacity:${enabled ? 1 : 0.45}">
      <input type="checkbox" data-action="toggle-fame" data-id="${t.id}" ${checked ? "checked" : ""} ${enabled ? "" : "disabled"}>
      <span>需累積 ${t.threshold} 點｜${t.desc}</span>
    </label>`;
  }).join("");

  return `
    <div class="panel">
      <h2>新馬生成</h2>
      <p class="muted">為牠取個名字，開始牠的三年生涯。</p>
      <input type="text" id="horseNameInput" placeholder="馬匹名稱" value="${escapeHtml(UI.state.horseNameInput || h.name)}" oninput="UI.state.horseNameInput=this.value" style="width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;margin-bottom:10px;">
      <div class="between">
        <div>${tierBadge(h.qualityTier, h.qualityTierName)} <span class="muted">總點數約 ${Object.values(h.stats).reduce((a,b)=>a+b,0)}</span></div>
        <button class="btn secondary" data-action="regen-horse">重新生成</button>
      </div>
      <div class="stat-grid">
        <div class="stat-line"><span>速度</span><b>${Math.round(h.stats.speed)}</b></div>
        <div class="stat-line"><span>耐力</span><b>${Math.round(h.stats.stamina)}</b></div>
        <div class="stat-line"><span>爆發力</span><b>${Math.round(h.stats.power)}</b></div>
        <div class="stat-line"><span>幸運/穩定性</span><b>${Math.round(h.stats.luck)}</b></div>
      </div>
      <h3>距離適性</h3>
      ${renderAptitudeGrid(h.aptitudes.distanceGrades)}
      <h3>跑法適性（點選以選擇本輪主要跑法）</h3>
      ${renderStyleGrid(h)}
    </div>
    <div class="panel">
      <h3>名聲點數兌換（目前累積 ${fmtNum(meta.legacyFamePoints)} 點）</h3>
      ${fameOptions}
    </div>
    <div class="panel center">
      <button class="btn block" data-action="confirm-new-horse">確認並開始生涯</button>
      <button class="btn block secondary" data-action="back-to-title">返回標題</button>
    </div>
  `;
}

// ---------- 生涯主畫面 ----------
function renderStatusBar() {
  const c = gameState.currentRun.career;
  const stage = getStage(c.turn);
  return `
    <div class="statusbar">
      <div class="between">
        <span class="turn-label">第 ${c.turn} / ${TOTAL_TURNS} 回合・${stage.name}</span>
        <span>💰 ${fmtNum(c.money)}｜⭐ ${fmtNum(c.reputation)}</span>
      </div>
      <div class="muted">體力</div>
      <div class="bar-track"><div class="bar-fill energy" style="width:${c.energy}%"></div></div>
      <div class="muted">疲勞 ${c.fatigue >= FATIGUE_WARN_THRESHOLD ? '<span class="warn-text">（偏高）</span>' : ""}</div>
      <div class="bar-track"><div class="bar-fill fatigue" style="width:${c.fatigue}%"></div></div>
    </div>
  `;
}

// 唯讀版跑法適性格線（生涯主畫面用，不可點選切換跑法，避免跟新馬生成畫面的可選版混淆）
function renderStyleGridReadonly(h) {
  return `<div class="aptitude-grid">${STYLE_LIST.map((s) => `
    <div class="aptitude-cell ${h.chosenStyle === s.id ? "selected" : ""}">
      <div>${s.name}</div><div class="badge grade-${h.aptitudes.styleGrades[s.id]}">${h.aptitudes.styleGrades[s.id]}</div>
    </div>`).join("")}</div>`;
}

// 生涯主畫面的距離／跑法適性摘要，預設收合，供玩家隨時查看忘記的適性（不可在此變更主戰跑法）
function renderHorseAptitudeSummary(h) {
  return `
    <details class="aptitude-summary">
      <summary>查看距離／跑法適性</summary>
      <h3>距離適性</h3>
      ${renderAptitudeGrid(h.aptitudes.distanceGrades)}
      <h3>跑法適性（主戰：${styleLabel(h.chosenStyle)}）</h3>
      ${renderStyleGridReadonly(h)}
    </details>
  `;
}

function renderHorsePanel() {
  const h = gameState.currentRun.horse;
  return `
    <div class="panel">
      <div class="between"><h2>${escapeHtml(h.name)}</h2>${tierBadge(h.qualityTier, h.qualityTierName)}</div>
      <div class="stat-grid">
        <div class="stat-line"><span>速度</span><b>${Math.round(h.stats.speed)}</b></div>
        <div class="stat-line"><span>耐力</span><b>${Math.round(h.stats.stamina)}</b></div>
        <div class="stat-line"><span>爆發力</span><b>${Math.round(h.stats.power)}</b></div>
        <div class="stat-line"><span>幸運/穩定性</span><b>${Math.round(h.stats.luck)}</b></div>
      </div>
      <p class="muted">主戰跑法：${styleLabel(h.chosenStyle)}｜屬性上限 ${effectiveStatCap(h)}</p>
      ${renderHorseAptitudeSummary(h)}
    </div>
  `;
}

function renderCareerMain() {
  const state = gameState;
  const career = state.currentRun.career;
  const stage = getStage(career.turn);
  const scheduledRace = getScheduledRace(state);
  const isMandatoryRace = !!scheduledRace && scheduledRace.grade === "maiden";

  let actionHtml = "";
  if (isMandatoryRace) {
    actionHtml += `<p class="muted">新馬戰是生涯必經的第一戰，本回合必須出賽，無法訓練或休息。</p>`;
  } else if (!stage.trainingAllowed) {
    actionHtml += `<p class="muted">引退期不開放訓練，只能選擇休息${scheduledRace ? "或出賽" : ""}。</p>`;
  } else {
    actionHtml += `<h3>訓練</h3><div class="row">`;
    ["speed", "stamina", "power", "luck"].forEach((stat) => {
      actionHtml += `<button class="btn secondary" data-action="do-train" data-intensity="standard" data-stat="${stat}">標準・${statLabel(stat)}</button>`;
    });
    actionHtml += `</div><div class="row">`;
    ["speed", "stamina", "power", "luck"].forEach((stat) => {
      actionHtml += `<button class="btn secondary" data-action="do-train" data-intensity="light" data-stat="${stat}">輕度・${statLabel(stat)}</button>`;
    });
    actionHtml += `</div><div class="row">`;
    ["speed", "stamina", "power", "luck"].forEach((stat) => {
      actionHtml += `<button class="btn secondary" data-action="do-train" data-intensity="intense" data-stat="${stat}">強化・${statLabel(stat)}</button>`;
    });
    actionHtml += `</div>`;
  }

  actionHtml += `<h3>其他行動</h3><div class="row">
    ${isMandatoryRace ? "" : `<button class="btn" data-action="do-rest">休息</button>`}
    ${scheduledRace ? `<button class="btn danger" data-action="go-race-preview">出賽：${scheduledRace.name}</button>` : ""}
  </div>`;

  const streak = career.trainingStreak;
  const streakText = streak.stat ? `<p class="muted">連續訓練：${statLabel(streak.stat)} × ${streak.count}</p>` : "";

  return `
    ${renderStatusBar()}
    ${renderHorsePanel()}
    <div class="panel">
      ${actionHtml}
      ${streakText}
    </div>
  `;
}

// ---------- 比賽畫面 ----------
function renderRacePreview() {
  const def = UI.state.currentRaceDef;
  const gradeInfo = GRADE_INFO[def.grade];
  let distancePicker = "";
  if (def.grade === "retirementRace") {
    distancePicker = `<h3>選擇引退紀念賽距離</h3><div class="row">
      ${DISTANCE_CAT_ORDER.map((catId) => `<button class="btn ${UI.state.retireDistanceCat === catId ? "" : "secondary"}" data-action="select-retire-distance" data-cat="${catId}">${distanceCatLabel(catId)}（${RETIREMENT_DISTANCE_MAP[catId]}m）</button>`).join("")}
    </div>`;
  } else if (def.grade === "maiden") {
    distancePicker = `<h3>選擇新馬戰出賽距離</h3>
      <p class="muted">請選擇這匹馬要挑戰哪一種距離。若這場未獲勝，第6、8回合的未勝利賽會自動沿用這裡選擇的距離，不會再問一次。</p>
      <div class="row">
      ${DISTANCE_CAT_ORDER.map((catId) => `<button class="btn ${UI.state.maidenDistanceCat === catId ? "" : "secondary"}" data-action="select-maiden-distance" data-cat="${catId}">${distanceCatLabel(catId)}（${RETIREMENT_DISTANCE_MAP[catId]}m）</button>`).join("")}
    </div>`;
  }
  const distanceCat = def.grade === "retirementRace" ? UI.state.retireDistanceCat
    : def.grade === "maiden" ? UI.state.maidenDistanceCat
    : def.distanceCat;
  const distance = distanceCat ? RETIREMENT_DISTANCE_MAP[distanceCat] : null;
  const canConfirm = def.grade !== "maiden" || !!UI.state.maidenDistanceCat;

  return `
    ${renderStatusBar()}
    <div class="panel">
      <h2>${def.name}</h2>
      <p>${gradeBadge(def.grade === "retirementRace" ? "特別賽" : gradeInfo.name)} ${distanceCat ? `${distanceCatLabel(distanceCat)}（${distance}m）` : "尚未選擇距離"}</p>
      <p class="muted">出賽馬數：${gradeInfo.fieldSize} 匹（含玩家）</p>
      ${distancePicker}
      <div class="row">
        <button class="btn danger" data-action="confirm-race" ${canConfirm ? "" : "disabled"}>確認出賽</button>
        <button class="btn secondary" data-action="back-to-career">取消，返回</button>
      </div>
    </div>
  `;
}

function renderRaceAnim() {
  const sim = UI.state.lastActionResult.raceSimResult;
  const tick = Math.min(UI.state.animTick, sim.numTicks - 1);
  const playerGate = sim.playerEntry.gate;
  // v0.1.1修正：賽道列順序改依閘位號碼固定排列（複本排序，不動到 sim.entries 原始順序），
  // 避免動畫還沒跑完，列的上下順序就先透露最終名次。
  const laneOrder = sim.entries.slice().sort((a, b) => a.gate - b.gate);
  const rows = laneOrder.map((e) => {
    const progress = clamp((e.log[tick] || 0), 0, 100);
    return `<div class="track">
      <div class="finish-line"></div>
      <div class="marker ${e.isPlayer ? "player" : ""}" style="left:${progress}%">[${e.gate}] ${escapeHtml(e.name)}</div>
    </div>`;
  }).join("");
  return `
    <div class="panel">
      <h2>比賽進行中…</h2>
      <p class="muted">你的閘位：第 ${playerGate} 閘（共 ${sim.entries.length} 閘，號碼越小越靠內側）</p>
      ${rows}
    </div>
  `;
}

function startRaceAnimation() {
  if (UI.state.animTimer) clearInterval(UI.state.animTimer);
  const sim = UI.state.lastActionResult.raceSimResult;
  UI.state.animTick = 0;
  UI.state.animTimer = setInterval(() => {
    UI.state.animTick += 1;
    if (UI.state.animTick >= sim.numTicks) {
      clearInterval(UI.state.animTimer);
      UI.state.animTimer = null;
      UI.state.screen = "raceResult";
      renderApp();
      return;
    }
    renderApp();
  }, 140);
}

function renderRaceResult() {
  const result = UI.state.lastActionResult;
  const sim = result.raceSimResult;
  // v0.1.1修正：結果列表依名次排序（複本排序，sim.entries 本身已不再保證是名次順序）。
  const rankedEntries = sim.entries.slice().sort((a, b) => a.placement - b.placement);
  const rows = rankedEntries.map((e) => `
    <div class="result-row ${e.isPlayer ? "player" : ""}">
      <span>${e.placement}. [${e.gate}] ${escapeHtml(e.name)}</span>
      <span>${formatTime(e.time)}</span>
    </div>
  `).join("");
  return `
    <div class="panel">
      <h2>比賽結果</h2>
      ${rows}
      <hr>
      <p>名次：<b>第 ${result.finalPlacement} 名</b></p>
      <p>獎金 +${fmtNum(result.prize)}｜聲望 +${fmtNum(result.rep)}</p>
      <div class="center"><button class="btn block" data-action="race-continue">繼續</button></div>
    </div>
  `;
}

// ---------- 事件彈窗 ----------
function renderEventModal(ev) {
  return `
    <div class="event-overlay">
      <div class="event-box category-${ev.category}">
        <h2>${ev.name}</h2>
        <p>${ev.text}</p>
        <div class="center"><button class="btn block" data-action="dismiss-event">確認</button></div>
      </div>
    </div>
  `;
}

// ---------- 二次確認彈窗 ----------
function renderConfirmDialog(dialog) {
  const buttons = dialog.alertOnly
    ? `<button class="btn secondary" data-action="confirm-no">確定</button>`
    : `<button class="btn danger" data-action="confirm-yes">確定執行</button>
       <button class="btn secondary" data-action="confirm-no">取消</button>`;
  return `
    <div class="confirm-overlay">
      <div class="confirm-box">
        <h3>${dialog.title}</h3>
        <p>${dialog.text}</p>
        <div class="row">
          ${buttons}
        </div>
      </div>
    </div>
  `;
}

// ---------- 引退結算畫面 ----------
function renderRetirementSummary() {
  const s = UI.state.retirementSummary;
  const run = UI.state.finishedRun;
  const horse = run.horse;
  const career = run.career;
  const historyRows = career.raceHistory.map((r) => `
    <tr><td>${r.turn}</td><td>${r.raceName}</td><td>${GRADE_INFO[r.grade].name}</td><td>第${r.placement}名</td><td>${formatTime(r.time)}</td></tr>
  `).join("");
  return `
    <div class="panel center">
      <h1>${s.title}</h1>
      <p class="muted">${escapeHtml(horse.name)}（引退原因：${RETIREMENT_REASON_LABEL[career.retirementReason] || career.retirementReason}）</p>
      <h2>總評分數：${s.total}</h2>
    </div>
    <div class="panel">
      <div class="stat-grid">
        <div class="stat-line"><span>戰績分</span><b>${Math.round(s.raceScore)}</b></div>
        <div class="stat-line"><span>聲望分</span><b>${Math.round(s.repScore)}</b></div>
        <div class="stat-line"><span>屬性分</span><b>${Math.round(s.statScore)}</b></div>
        <div class="stat-line"><span>特殊加分</span><b>${Math.round(s.specialScore)}</b></div>
      </div>
      <p class="muted">生涯完整度倍率 ×${s.completeness}</p>
    </div>
    <div class="panel">
      <h3>最終屬性</h3>
      <div class="stat-grid">
        <div class="stat-line"><span>速度</span><b>${Math.round(horse.stats.speed)}</b></div>
        <div class="stat-line"><span>耐力</span><b>${Math.round(horse.stats.stamina)}</b></div>
        <div class="stat-line"><span>爆發力</span><b>${Math.round(horse.stats.power)}</b></div>
        <div class="stat-line"><span>幸運/穩定性</span><b>${Math.round(horse.stats.luck)}</b></div>
      </div>
      <h3>戰績列表</h3>
      ${historyRows ? `<table class="history"><tr><th>回合</th><th>賽事</th><th>等級</th><th>名次</th><th>時間</th></tr>${historyRows}</table>` : `<p class="muted">生涯尚未出賽過</p>`}
      <p>累積獎金：${fmtNum(career.money)}｜累積聲望：${fmtNum(career.reputation)}</p>
      <p>換算名聲點數：+${fmtNum(s.famePointsEarned)}</p>
    </div>
    <div class="panel center">
      <button class="btn block" data-action="back-to-title">返回標題畫面</button>
    </div>
  `;
}
