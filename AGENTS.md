# EMS Agent 入口

本檔是接手導覽；完整工作規範在 [project_rules.md](project_rules.md)，文件與程式地圖在 [doc/README.md](doc/README.md)。

## 目前採集測試交接（2026-11-12）

接續硬體／採集測試時，優先讀[溫度 → Pi → EMS 交接](doc/operations/edge-temperature-handoff-20261112.md)。內含使用者最新範圍、未完成清單、測試證據及從 T0 開始的順序。日照已移出本輪；必須由 Pi 解析並傳送，不能交付成電腦直傳。先核對活動 24h 長測 status，不占用 COM3／COM4 或改其凍結來源。Pi／ADTEK 全鏈路尚未驗收，既有 Windows Delta 台架結果不能代替。

## 開始工作

1. 確認權威 checkout 為 `/home/dalelin/synaiq/EMS`，先查看 `git status --short`，保留既有未提交變更。Windows 的 `C:\Users\User\synaiq\EMS` 是備份，不在該副本開發。
2. 先讀 [project_rules.md](project_rules.md) 與 [PRD Guideline](doc/PRD-架構設計-Guideline.md)。
3. 用 [任務地圖](doc/README.md) 找相關 PRD，再依 project_rules §14 讀相關 PRD 全文、三張 C4／資料流圖、相關 ADR、風險及威脅模型，才修改程式或設定。
4. 查實際狀態時，交叉核對 PRD／ADR 狀態、來源程式、Compose／migration 及相應驗證紀錄；文件存在或被列入地圖不代表已實作或部署。

## 維護入口

新增／搬移關鍵文件、程式模組或變更實作狀態時，同步 [doc/README.md](doc/README.md) 及對應 PRD／ADR／架構索引，驗證相對連結。規範與契約仍維護在原權威文件，地圖只負責定位。
