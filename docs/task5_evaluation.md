# CarbonLens 任務五評估紀錄

## V2.3 部署前現況

檢查日期為 2026-11-13。檢查對象為目前工作區的 Phase 3 程式。

| 項目 | 實際觀察 |
| --- | --- |
| Git 版本 | 分支 master，尚無 commit，全部專案檔案尚未追蹤 |
| GitHub Repository | git remote -v 沒有輸出，尚未建立本機遠端連結 |
| 本機服務 | http://127.0.0.1:8501/_stcore/health 回傳 HTTP 200 與 ok |
| 自動化測試 | 本次重新執行 pytest，53 passed in 5.68s |
| 測試環境 | Windows、Python 3.12.14、Pandas 3.0.1、Plotly 7.1.0、PyArrow 21.0.0、Streamlit 1.67.0、pytest 9.2.0、tzdata 2026.6 |
| 環境限制 | 系統 python 指令指向不可執行的 WindowsApps 別名；本次用 Codex 隨附 Python 與工作區套件路徑。標準 .venv/Scripts/python.exe 尚不存在 |
| 設定存在性 | 工作區 .env、.env.example、.streamlit/secrets.toml 尚不存在。程序環境的 OPENAI_API_KEY、OPENAI_MODEL、DATABASE_URL 尚未設定 |
| 機密排除 | git check-ignore 確認 .env、.streamlit/secrets.toml 與 runtime 內 SQLite 檔符合忽略規則 |
| 真實模型 | 尚未實作及呼叫 |
| 公開 HTTPS 網址 | 尚未取得或驗證 |
| 公開部署日期／commit | 待部署後填入 |

本次測試沿用既有驗證、計算與 Streamlit AppTest，包含三檔示範、數值邊界、CSV 格式、來源列、缺值與手動門檻確認。既有瀏覽器驗證的詳細紀錄見 [testing.md](testing.md)。本次服務健康檢查只證明當時本機服務有回應。

重現本機測試時，使用有效 Python 環境安裝 requirements.txt，再執行 python -m pytest -q。本次 Codex 使用既有 .venv/phase3-compatible、.venv/phase3-deps 與 .venv/phase2-deps 的套件，設定 STREAMLIT_GLOBAL_DEVELOPMENT_MODE=false，並以 --basetemp 指定工作區內全新的暫存目錄。這項環境紀錄供維護者查驗，雲端使用者透過網址操作。

## 公開網站實測表

以下狀態皆為尚未執行。部署取得實際網址後逐項填寫日期、預期與實際結果、證據、失敗原因和重測結果。

| 編號 | 公開操作 | 預期 | 實際結果／證據 |
| --- | --- | --- | --- |
| P01 | 從新瀏覽器開啟 HTTPS 網址 | 首頁、Dashboard 與品牌正常，使用者端免安裝 | 尚未執行，缺公開網址 |
| P02 | 正常上傳三份 CSV 並選基準 | 案件與基準可選，來源保持可追溯 | 尚未執行 |
| P03 | 上傳缺欄、無效數字與超過大小限制的檔案 | 顯示具體問題並阻止不完整分析 | 尚未執行 |
| P04 | 授權使用者啟動 Real 模式 | 保存模型名稱、請求識別碼、宣稱欄位、使用量與工具呼叫紀錄 | 尚未執行，缺 Agent |
| P05 | 執行 SYN001／SYN002／SYN003 | WACI 分別為 50／95／空值，判定為符合／不一致／資料不足 | 尚未執行 |
| P06 | 檢視圖表與原始證據 | 圖表依實際輸入，引用同一案件資料版本 | 尚未執行 |
| P07 | 確認、修正、退回並重跑 | 舊版可追溯，修正後重新計算，意見與時間保存 | 尚未執行，缺覆核流程 |
| P08 | 下載分析報告 | 檔名含 CarbonLens，中文、缺值、版本及覆核資料正確 | 尚未執行，缺報告匯出 |
| P09 | 未授權呼叫、超限及 API 故障 | 伺服器阻止付費呼叫或顯示可重試錯誤，避免重複收費請求 | 尚未執行 |
| P10 | 使用者 A 與 B 各上傳、查看與下載 | 互相無法讀寫對方案件，已知案件 ID 也受權限檢查 | 尚未執行 |
| P11 | 重整、登出及雲端重啟 | 行為符合已選儲存方案；持久化模式重新登入可取回自己的覆核紀錄 | 尚未執行 |
| P12 | 檢查原始碼、瀏覽器與下載內容 | API Key 不出現在這些輸出；API 設定只在伺服器使用 | 尚未執行 |

各次公開測試須記錄實際網址、部署 commit、Python 與模型版本、測試者角色、資料來源及測試時間。模型準確率、召回率、誤報率與人工時間改善依 [testing.md](testing.md) 的公式評估，現階段均未量測。

## 2026-11-13 功能整合進度

- 新增設定載入、授權登入、Real 結構化擷取、Mock 示範、程式工具紀錄、額度預留、SQLite/PostgreSQL 儲存介面、覆核與 JSON/Markdown 下載。
- 更新後 pytest：59 passed in 5.82s，包含原有 53 項及 6 項新流程測試。
- 新測試涵蓋帳號隔離、版本衝突、額度交易、重複呼叫阻擋、未授權阻擋、覆核重算及序列化。
- 已建立 .venv/runtime，Python 3.12.14；本機以 python -m streamlit run app.py 啟動於 8502。
- 真實 API 已嘗試兩次，均收到 RateLimitError；無成功模型輸出。錯誤尚無法區分餘額與暫時限流，不列為通過。
- 目前模型使用 Structured Outputs 擷取，由程式編排驗證與 WACI；尚未實作由模型選擇工具的 function calling，不得將程式事件稱為模型工具呼叫成功。
- GitHub 內建瀏覽器需要使用者登入；尚無 Repository 遠端及公開 HTTPS 網址。
- 上表為前次檢查快照；公開 P01–P12 仍待實測。PostgreSQL 介面尚未連接真實服務驗證。

### 同日補充：模型工具呼叫

- Real 已改用 Responses API 的嚴格 function calling，模型提交 analyze_claim 欄位，後端驗證參數與原文並執行數值工具，保存 tool_call_id。
- 採單次模型請求、指定工具的有界工作流程，最終結論由 Python 回傳；不使用模型自由文字計算 WACI。
- 新增 SDK 回應替身測試，驗證工具參數與不合法回應攔截。最新結果：60 passed in 6.01s。
- 替身測試不代表真實 API 成功；目前仍因 RateLimitError 待驗證。

## 2026-11-13 GitHub 與部署進度

- 已建立並推送 https://github.com/xr1624/CarbonLens ，部署分支 codex/deploy，程式版本 a9a758a。
- 已在 Streamlit Community Cloud 指定 app.py、Python 3.12，使用者已貼入並儲存 Secrets。
- 已提交 Deploy，平台導向 https://carbonlens-xr1624.streamlit.app/ ，當下顯示 Your app is in the oven，尚未判定啟動成功。
- 最新本機測試：60 passed in 6.45s。公開核心功能待啟動後測試。
