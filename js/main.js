// main.js — 事件綁定與畫面流程控制
"use strict";

window.gameState = null;

function afterActionResult(result) {
  UI.state.lastActionResult = result;
  if (result.eventResult) {
    UI.state.eventToShow = result.eventResult;
    UI.state.pendingAfterEvent = result.ended ? "retirement" : "careerMain";
    renderApp();
  } else if (result.ended) {
    goToRetirement();
  } else {
    UI.state.screen = "careerMain";
    renderApp();
  }
}

function goToRetirement() {
  UI.state.finishedRun = deepClone(gameState.currentRun);
  UI.state.retirementSummary = finalizeRunAndGetSummary(gameState);
  UI.state.screen = "retirementSummary";
  renderApp();
}

function handleTrain(intensity, stat, forceConfirmed) {
  const career = gameState.currentRun.career;
  if (intensity === "intense" && career.fatigue >= FATIGUE_WARN_THRESHOLD && !forceConfirmed) {
    UI.state.confirmDialog = {
      title: "高風險警告",
      text: `目前疲勞值已達 ${career.fatigue}，強化訓練有較高受傷、甚至提前引退的風險，確定要執行嗎？`,
      onYes: () => handleTrain(intensity, stat, true),
    };
    renderApp();
    return;
  }
  const result = doTrainingAction(gameState, intensity, stat);
  afterActionResult(result);
}

function handleRest() {
  const result = doRestAction(gameState);
  afterActionResult(result);
}

function handleConfirmRace() {
  const def = UI.state.currentRaceDef;
  const result = doRaceAction(gameState, def, UI.state.retireDistanceCat);
  UI.state.lastActionResult = result;
  UI.state.screen = "raceAnim";
  renderApp();
  startRaceAnimation();
}

function handleAction(action, el) {
  switch (action) {
    case "new-game":
      UI.state.previewHorse = generateHorse("新星");
      UI.state.selectedFame = [];
      UI.state.horseNameInput = "";
      UI.state.screen = "newHorse";
      renderApp();
      break;
    case "continue-game":
      UI.state.screen = "careerMain";
      renderApp();
      break;
    case "regen-horse":
      UI.state.previewHorse = generateHorse(document.getElementById("horseNameInput") ? document.getElementById("horseNameInput").value : "新星");
      renderApp();
      break;
    case "select-style":
      UI.state.previewHorse.chosenStyle = el.dataset.style;
      renderApp();
      break;
    case "toggle-fame": {
      const id = el.dataset.id;
      const idx = UI.state.selectedFame.indexOf(id);
      if (idx >= 0) UI.state.selectedFame.splice(idx, 1);
      else UI.state.selectedFame.push(id);
      renderApp();
      break;
    }
    case "confirm-new-horse": {
      const nameInput = document.getElementById("horseNameInput");
      const name = (nameInput && nameInput.value.trim()) || "無名馬";
      UI.state.previewHorse.name = name;
      startNewRun(gameState, UI.state.previewHorse, UI.state.selectedFame);
      UI.state.previewHorse = null;
      UI.state.screen = "careerMain";
      renderApp();
      break;
    }
    case "back-to-title":
      UI.state.screen = "title";
      renderApp();
      break;
    case "do-train":
      handleTrain(el.dataset.intensity, el.dataset.stat, false);
      break;
    case "do-rest":
      handleRest();
      break;
    case "go-race-preview":
      UI.state.currentRaceDef = getScheduledRace(gameState);
      UI.state.retireDistanceCat = "mile";
      UI.state.screen = "racePreview";
      renderApp();
      break;
    case "select-retire-distance":
      UI.state.retireDistanceCat = el.dataset.cat;
      renderApp();
      break;
    case "confirm-race":
      handleConfirmRace();
      break;
    case "back-to-career":
      UI.state.screen = "careerMain";
      renderApp();
      break;
    case "race-continue":
      afterActionResult(UI.state.lastActionResult);
      break;
    case "dismiss-event": {
      UI.state.eventToShow = null;
      const pending = UI.state.pendingAfterEvent;
      UI.state.pendingAfterEvent = null;
      if (pending === "retirement") goToRetirement();
      else { UI.state.screen = "careerMain"; renderApp(); }
      break;
    }
    case "confirm-yes": {
      const dialog = UI.state.confirmDialog;
      UI.state.confirmDialog = null;
      if (dialog && dialog.onYes) dialog.onYes();
      break;
    }
    case "confirm-no":
      UI.state.confirmDialog = null;
      renderApp();
      break;
    default:
      break;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  gameState = loadState();
  UI.state.screen = "title";
  renderApp();

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    handleAction(el.dataset.action, el);
  });
});
