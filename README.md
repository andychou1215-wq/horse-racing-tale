# 賽馬物語 Horse Racing Tale — 可玩原型

依專案 12 份規格文件（overview / game-loop / horse-generation / training-mechanics /
race-simulation / events / race-calendar / ai-opponents / retirement-summary /
art-style / data-structure / ui-flow）實作的第一版純前端可玩原型。

## 怎麼玩

不需要安裝任何東西，直接用瀏覽器打開 `index.html` 即可開始遊玩。
（若瀏覽器對 `file://` 開啟的頁面限制 localStorage，存檔可能無法在重新整理後保留——
遊戲仍可正常遊玩，只是離開頁面後進度不會保存。如果想要穩定存檔，可以用任何簡易
本機伺服器打開，例如在此資料夾執行 `python -m http.server` 後瀏覽
`http://localhost:8000/`。）

## 目前完成度

七個畫面（標題／新馬生成／生涯主畫面／比賽畫面／事件彈窗／引退結算／二次確認）與
規格書列出的所有核心系統都已可運作並串接：

- 36 回合生涯迴圈、四階段（新星期／成長期／巔峰期／引退期）
- 訓練（輕度／標準／強化）、休息、體力／疲勞公式與受傷風險
- 馬匹生成（品質等級、距離傾向軸、跑法適性）與 AI 對手生成
- Tick 制比賽模擬（20 tick、三階段、跑法係數、距離耐力需求、完賽時間換算）
- 32 個隨機事件（含分層機率判定與稀有提前結束事件）
- 賽事日曆（含新星期新馬賽／未勝利賽分支與安全機制）
- 引退結算總評公式、稱號分級、名聲點數跨輪迴兌換
- localStorage 存讀檔

## 原型階段的簡化與待調整項目（原始文件未明訂數值處）

這些是規格書沒有給出精確數字、原型階段先用合理預設值頂上的地方，之後可以邊玩邊調：

- `js/constants.js` 的 `BASE_GROWTH`（訓練成長公式的基礎值）與
  `TIME_CONVERSION_COEF`（完賽時間換算係數）。
- `js/raceSim.js` 的跑法風格階段係數（`STYLE_PHASE_POWER` / `STYLE_PHASE_FATIGUE`）是
  依文件的文字敘述量化出來的參數，用來讓領逃／先行／居中／後追四種跑法在起跑、中盤、
  衝刺三階段有不同表現。
- **受傷機制的處理方式**：文件裡「受傷機率」公式本身沒有明講觸發後的後果。原型採用
  「觸發時造成額外疲勞衝擊（+15），是否強制引退完全交給疲勞 ≥95 的累積型判定（20%）
  來決定」，而不是讓受傷機率直接、獨立地結束生涯。這是刻意選的設計——如果讓受傷機率
  直接結束生涯，強化訓練會變成幾乎必死的選項（實測隨機測試機器人 300 輪幾乎全部在
  10 回合內因此提前結束），讓「休息管理疲勞」這個文件中強調的核心策略失去意義。
  如果想要更貼近字面公式，可以在 `js/training.js` / `js/state.js` 中調整。
- 「贊助商邀約」事件要求下回合指定出賽，「比賽失誤」事件調整名次等文字效果，原型做了
  簡化實作（多數改為套用到下一場比賽的暫時 buff，而非強制指定賽事）。

## 測試

`test/smoke.js`：用 Node `vm` 模組載入所有邏輯檔案，自動跑 300 輪生涯（不含 UI），
檢查不會拋錯、統計引退原因與稱號分布。

```
node test/smoke.js
```

`test/dom-smoke.js`：用 jsdom 載入整個網頁、模擬點擊跑完一整輪生涯（含比賽動畫、
事件彈窗、引退結算），需要先 `npm install jsdom` 才能執行。

```
npm install jsdom
node test/dom-smoke.js
```

## 檔案結構

```
index.html          單頁應用進入點
css/style.css        版面與配色（純文字/資料呈現風，art-style.md）
js/constants.js       全域數值設定
js/utils.js           共用工具函式
js/horseGen.js        馬匹生成（horse-generation.md）
js/aiOpponents.js     AI對手生成（ai-opponents.md）
js/training.js        訓練/體力公式（training-mechanics.md）
js/raceSim.js         比賽模擬（race-simulation.md）
js/events.js          隨機事件（events.md）
js/retirement.js      引退結算（retirement-summary.md）
js/state.js           存讀檔與生涯流程（data-structure.md + game-loop.md）
js/ui.js              畫面渲染（ui-flow.md）
js/main.js            事件綁定與流程控制
test/                 自動化測試腳本
```
