# Claude EMS 前端接手紀錄

日期：2026-09-23
來源：Claude session 154617c8-7994-43c5-aa4f-6cc0267f8afc / scratchpad/ems-design

## 已完成
- 將 51 個設計檔完整複製至本目錄 ems-design/，複製時逐檔 SHA-256 相符；清單見 source-manifest.json。
- 另保存 taistro-logo/ 官方標誌素材與 SESSION-PROGRESS.md。
- 重新執行 ems-design/check.mjs：7 張畫面及 canvas.json 通過，0 errors / 0 warnings。此腳本會重寫副本中的 check.txt；manifest 記錄的是來源檔案雜湊。
- 重新執行 ems-design/css/css-lint.mjs：PASS，0 failures；包含 280 tokens、237 class names。報告見 css-validation.txt。
- 已讀取現有 frontend/package.json、src/app/router.tsx、src/app/AppShell.tsx 及 Git status。

## 接手基準
七畫面：Main、Monitor、Demand、Storage、Alarms、Devices、Reports。
設計採官方 tAIstro SVG、深色頁首及側欄、紙白內容區、橄欖綠與金色；詳細契約見 ems-design/css/STYLE-GUIDE.md。
現有應用為 React 19、Vite 7、TypeScript、Tailwind 4，已有受保護的設備清單、設備詳情、確認佇列、審核與 Gallery 路由。

## 尚未完成／不可視為完成
- 原稿為 Claude Design 格式，依賴 ./support.js、x-dc 及模板綁定；本套件未包含 support.js，不能直接作為一般網頁交付。
- 本次僅完成靜態驗證，未驗證瀏覽器視覺或互動，未驗證 Claude 線上畫布。
- API-MAPPING.md 已存在；其 20 已實作 / 49 規劃中 / 24 缺口的統計為 Claude 文件主張，本次未重新逐一查證端點。
- ems-design/prd/PRD-0017-console-data-api-gaps.md 尚有 SKELETON 及 FROM-MAPPING 標記，屬未完成草稿。
- 七畫面尚未整合至現有 React 應用，也未接通真實 API。

## 下一階段順序
1. 依專案 project_rules.md 完成 PRD-0005 與相關架構／ADR 閱讀，將設計需求對照既有路由與功能。
2. 建立不依賴 Claude 執行環境的可預覽七畫面，先保留設計外觀並明確標示示意資料；核對桌面、窄螢幕與互動。
3. 將共用外殼與元件逐步整合 React；保留既有登入授權、設備及審核功能，避免覆蓋現有未提交的主題修改。
4. 逐項核對 API-MAPPING 並完成 PRD 草稿；僅串接已確認存在的端點。

## 變更範圍
本次只新增獨立交接目錄，沒有修改 frontend/、正式 PRD、API 或任何部署設定，沒有 commit/push/deploy。
原始 Windows 暫存資料保持原樣。專案原先已有多個未提交的前端與文件變更，後續必須保留。

## 2026-09-23 後續：可瀏覽預覽已架設
已於 output/ems-design-preview-20260923 建立獨立預覽，入口 http://127.0.0.1:4178/。
沿用找到的 Claude dc-runtime.js 作為 support.js，七頁已通過實際瀏覽器渲染與導航檢查。
能源總覽警示／正常及儲能四種情境可切換。已視覺檢查主頁桌面與手機寬度。
這補足前述「原稿不能直接預覽」的缺口；React 整合、API 串接與 PRD 草稿狀態仍維持未完成。
操作、重啟指令與限制見該預覽目錄 README.md。
