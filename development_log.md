# CarbonLens 開發紀錄

## 2026-11-13 · V2.3 公開部署前評估

- **Prompt**：將公開 HTTPS 網站操作納入任務四、五，先檢查現況、缺少功能及授權需求，確認後逐步部署。
- **開發內容**：核對實際程式、依賴、忽略規則與 Git 狀態，新增公開驗收條件與尚待執行的測試表，更新部署順序與 Python 版本規劃。
- **修改檔案**：docs/assignment_checklist.md、docs/task5_evaluation.md、docs/deployment.md、README.md、development_log.md。
- **測試結果**：本次重跑 53 項 pytest 全數通過，耗時 5.68 秒。本機服務健康檢查回傳 HTTP 200 與 ok。專案尚無 commit 或 remote，尚未取得公開 HTTPS 網址。
- **檢查與修正**：目前基準由 CSV 指定，AI、覆核、報告匯出及付費存取控制待加入。標準 python 指令仍有 WindowsApps 別名問題。部署版本建議改為與實測一致的 Python 3.12。使用者確認待進行。

## 2026-11-13 · Phase 3 Streamlit 網站與圖表

- **Prompt**：「確認無誤」，承接 V2.0 的 Phase 3，建立可操作的 Streamlit 表單、Dashboard 與圖表。
- **開發內容**：實作案件建立、CSV 上傳與欄位範本、人工確認門檻、瀏覽器工作階段的案件清單、四種 Plotly 圖表及來源證據。加入 CarbonLens 品牌圖示與響應式樣式。
- **修改檔案**：`app.py`、`src/charts.py`、`.streamlit/config.toml`、`assets/`、`tests/test_app.py`、`requirements.txt`、`README.md` 與架構、測試、部署文件。
- **測試結果**：53 項 pytest 通過。在本機瀏覽器驗證三檔示範基金、Dashboard、四張圖表、缺欄提示、完整 CSV 上傳與 390 像素寬版面。
- **檢查與修正**：初次啟動時新版 PyArrow 的 DLL 被 Windows 應用程式控制原則阻擋，指定 21.0.0 後通過。Phase 3 案件資料以瀏覽器工作階段保存。使用者覆核待進行。

## 2026-11-13 · Phase 2 合成資料與 WACI

- **Prompt**：「確認無誤」，承接 V2.0 的 Phase 2，建立三份合成 CSV、資料驗證與 WACI 模組。
- **開發內容**：完成合成資料、CSV 讀取、來源列追溯、逐案驗證、權重覆蓋率與精確門檻判定。Python 分析函式由呼叫端傳入已確認的宣稱目標。
- **修改檔案**：`data/` 三份 CSV、`src/validation.py`、`src/calculations.py`、`requirements.txt`、`tests/` 兩份測試、`README.md` 與架構、資料、測試文件。
- **測試結果**：51 項 pytest 通過，README 範例可執行。三案實測為 WACI 50、95、留空，實際降低 50%、5%、留空，覆蓋率 100%、100%、60%。
- **檢查與修正**：首次執行因沙箱預設暫存路徑無法建立而出現一項測試準備錯誤，改用工作區內的暫存路徑後全數通過。另確認 SYN003 的補件紀錄指向 `holdings.csv` 第 7 列。使用者覆核待進行。

## 2026-11-13 · 需求盤點與架構

- **Prompt**：「請先檢查目前專案資料夾」及「現在先完成 Phase 1，展示系統架構、資料夾結構、資料設計、Agent 流程圖與開發順序」。
- **開發內容**：確認工作區只有 Git 中繼資料，定義模組責任、案件快照、介面路徑與六階段交付順序。
- **修改檔案**：`README.md`、`docs/architecture.md`、`.gitignore`。
- **測試結果**：`git ls-files` 無既有追蹤檔案。`git check-ignore` 確認環境變數檔、Streamlit Secrets、本機資料庫路徑與虛擬環境符合忽略規則。
- **檢查與修正**：Codex 核對工作區與 V2.0 規格。Phase 3 的數值介面先使用可從原文核對的人工欄位，Phase 4 接上模型擷取。使用者覆核待進行。

## 2026-11-13 · 資料契約與數值標準

- **Prompt**：同一份 V2.0 規格要求三份 CSV、三檔示範基金、WACI、資料覆蓋率及資料可比較性檢查。
- **開發內容**：定義欄位、關聯與資料檢核。設計共用基準的三檔示範基金，建立手算標準答案。
- **修改檔案**：`docs/data_design.md`。
- **測試結果**：用 PowerShell 十進位運算核對標準答案。SYN001 與 SYN002 的 WACI 分別為 50、95，實際降低 50%、5%。SYN003 的覆蓋率為 60%，標準答案保留 WACI 與降低比例空值。
- **檢查與修正**：Codex 核對權重檢核、零值與空值差異，以及資料齊全但宣稱仍待確認的分支。採用權重合計精確等於 100% 的規則。使用者覆核待進行。

## 2026-11-13 · Agent 流程與驗收規劃

- **Prompt**：同一份 V2.0 規格要求分辨 AI 判斷、工具呼叫、確定性計算、資料來源與人工決策，並規劃 20 個以上獨立測試與公開部署驗證。
- **開發內容**：設計單一 Agent 分流與版本追溯，建立 Mermaid 流程圖，規劃自動化案例、真實模型評估、人工計時與公開部署檢查。
- **修改檔案**：`docs/agent_workflow.md`、`docs/testing.md`、`docs/deployment.md`、`development_log.md`。
- **測試結果**：使用 Codex 隨附的 Python 3.12.14 核對 README 的 6 個本機連結、3 檔案例的預期值及 28 個唯一的測試案例編號。Mermaid 靜態檢查核對 15 個節點、19 條連線與 5 類角色的引用，瀏覽器渲染待驗。使用 OpenAI 官方文件核對 Structured Outputs 設計。工作區的預設 `python` 啟動別名無法執行。
- **檢查與修正**：Codex 對齊資料不可比較、宣稱待確認與執行失敗的狀態，並要求修正欄位附可核對的證據。這三筆是同一次協作中實際完成的工作，後續階段將繼續記錄實作與使用者覆核。

## 2026-11-13 後端與 UI 整合

保留既有數值引擎與圖表，加入 Real/Mock 模式、function calling、授權登入、額度交易、案件版本與覆核、JSON/Markdown 匯出及 CSV 大小/筆數限制。60 項本機測試通過。API 真實嘗試遭 RateLimitError，尚未通過真實模型及公開網址驗收；等待 GitHub 登入。
