# 資料結構／存檔格式規劃

## 整體結構
單一 localStorage key，內含跨輪迴meta資料 + 當前生涯存檔：

```json
{
  "version": 1,
  "meta": { ... },
  "currentRun": { ... }
}
```

`currentRun` 為 `null` 代表沒有進行中的生涯（尚未開新馬，或上一輪已結算完畢）。

## meta（跨輪迴持久資料）

```json
"meta": {
  "legacyFamePoints": 0,
  "totalRunsCompleted": 0,
  "bestCareerScore": 0,
  "bestTitle": null,
  "personalBestTimes": {
    "1200": null, "1600": null, "2000": null, "2400": null, "3000": null
  },
  "runHistory": [
    { "horseName": "string", "title": "string", "score": 0, "completedAt": "ISO時間戳" }
  ]
}
```

- `legacyFamePoints`：對應 horse-generation.md 的名聲點數兌換，尚未兌換完的點數累積在此。
- `personalBestTimes`：支援 race-simulation.md 的「破紀錄」呈現。
- `runHistory`：簡單的歷代生涯清單，初版可只保留最近幾筆，之後可擴充成「名馬堂」。

## currentRun.horse（馬匹本體，對應 horse-generation.md）

```json
"horse": {
  "name": "string",
  "qualityTier": "不良|普通|優良|稀有",
  "stats": {
    "speed": 0, "stamina": 0, "power": 0, "luck": 0
  },
  "aptitudes": {
    "distanceMainPosition": 2.5,
    "distanceGrades": { "short": "B", "mile": "A", "middle": "B", "long": "D" },
    "styleGrades": { "front": "B", "pace": "A", "mid": "C", "closer": "D" }
  }
}
```

- `stats`：直接存當前永久數值（已含訓練成長與事件加成），套用增減時即時檢查160上限，不另存上限欄位（上限是全域常數）。
- `distanceGrades`/`styleGrades`：生成當下算好存起來，避免每次重新計算光譜距離。
- `distanceMainPosition`：保留原始值，因為名聲點數兌換（提升適性等級）需要微調此值後重新換算等級。

## currentRun.career（生涯進度）

```json
"career": {
  "turn": 1,
  "stage": "新星期",
  "energy": 100,
  "fatigue": 0,
  "money": 0,
  "reputation": 0,
  "maidenWon": null,
  "nonWinnerAttempts": 0,
  "openRaceUnlocked": false,
  "trainingStreak": { "stat": null, "count": 0 },
  "activeBuffs": [],
  "raceHistory": [],
  "eventLog": [],
  "isRetired": false,
  "retirementReason": null
}
```

- `maidenWon`：`null`(尚未比)/`true`/`false`，供 race-calendar.md 的分支邏輯判定。
- `openRaceUnlocked`：新馬賽獲勝、未勝利賽獲勝、或第10回合安全機制觸發時設為`true`。
- `trainingStreak`：追蹤「同屬性連續訓練N次」，供 events.md 的士氣低落／蛻變成長判定使用，更換訓練屬性即重置。
- `activeBuffs`：格式 `{ "target": "speed", "amount": 5, "scope": "nextRaceOnly" | { "expiresAtTurn": 12 } }`，統一存放事件/覺醒等暫時加成，套用時檢查170的暫時上限。
- `raceHistory`：每場比賽一筆 `{ "turn", "raceName", "grade", "distance", "placement", "time", "prizeEarned", "reputationEarned" }`，是 retirement-summary.md 計算戰績分與結算畫面戰績列表的資料來源。
- `eventLog`：每次觸發事件一筆 `{ "turn", "eventName", "category" }`，供 retirement-summary.md 的稀有正面事件次數統計使用。
- `retirementReason`：`"normal" | "重大傷病" | "醜聞風波" | "天災意外" | "伯樂相中" | "疲勞累積"`，決定 retirement-summary.md 的生涯完整度倍率。

## 存讀取邏輯
- **開新馬**：讀取`meta.legacyFamePoints`供兌換，扣除對應點數後生成新的`currentRun`，`meta`其餘欄位不變。
- **每回合結束**：整包覆寫`currentRun`到localStorage（資料量小，不需差量儲存）。
- **生涯結束（引退）**：依 retirement-summary.md 公式算出總評分數與稱號，更新`meta`（`legacyFamePoints`增加、`bestCareerScore`/`bestTitle`視情況更新、`personalBestTimes`比對更新、`runHistory`加一筆），接著把`currentRun`設回`null`。
