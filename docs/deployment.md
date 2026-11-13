# CarbonLens 部署計畫

本文件記錄 Phase 6 預定操作與公開網址的驗收方式。Phase 3 已在本機啟動及驗證 Streamlit 介面。GitHub 推送、公開網址及雲端驗證留待部署階段。

## V2.3 部署前評估

2026-11-13 檢查確認，根目錄已有 app.py、requirements.txt、.gitignore、.streamlit/config.toml、data 及 assets，檔案配置符合 Community Cloud 的基本結構。正式公開驗收還需要完成 Agent、覆核、報告、基準選擇與 API 存取控制，並在雲端 Linux 環境實際安裝及測試依賴。 [Streamlit 檔案配置](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)

建議課程展示採 Streamlit Community Cloud 承載 Python 後端與瀏覽器介面。官方目前提供免費 Community Cloud 託管；AI 呼叫用量另依實際模型與 API 帳戶設定管理。 [Streamlit Community Cloud](https://streamlit.io/cloud)

公開首頁與合成示範可開放瀏覽。付費分析採伺服器端驗證的展示帳號或存取碼，並限制每位使用者及全站呼叫量、原文長度和輸出 token。紀錄嘗試次數及用量，設定逾時與有限重試，避免重新繪製畫面時重複送出模型請求。這些是待實作方案。

先保留每個工作階段獨立的上傳資料與案件，加入當次覆核及報告下載。本機版本依原規格加入 SQLite。若採跨工作階段保存，建議透過統一儲存介面接 Supabase PostgreSQL，保存案件擁有者、分析版本、覆核與用量紀錄。每次讀寫及匯出都驗證擁有者。暫存型的程序內配額會在重啟後重設；需要跨重啟的額度與預算上限時，配額也使用持久化儲存。Community Cloud 本機檔案無法保證跨工作階段的持久性。 [Streamlit 資料連線與保存](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)

確認後依序完成以下工作。

1. 接入環境設定、真實 OpenAI 擷取與 Agent 分支，加入市場基準選擇、執行狀態與工具紀錄。
2. 完成人工覆核、版本記錄、資料保存與 CSV 報告，落實付費操作權限、用量限制與資料隔離。
3. 使用乾淨環境安裝 requirements.txt，驗證 python -m streamlit run app.py、全部測試與完整瀏覽器操作。
4. 準備發布檔案及提交，使用者登入 GitHub 並授權後推送 Repository。
5. 使用者登入 Community Cloud 並完成 GitHub 連接，選擇 Repository、分支、app.py 及 Python 3.12，在 Secrets 設定憑證後部署。
6. 記錄平台實際分配的 HTTPS 網址，逐項執行 [公開驗收清單](assignment_checklist.md)，把實測寫入 [任務五評估](task5_evaluation.md)。

## 本機啟動與依賴

從專案根目錄在 Python 3.12 的虛擬環境執行以下指令。現在本機實測為 Python 3.12.14，雲端預定選擇相同的 3.12 次版本。Community Cloud 在 Advanced settings 提供 Python 版本選單。 [Streamlit 部署設定](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

```powershell
python --version
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

在瀏覽器開啟 `http://localhost:8501`。`requirements.txt` 位於專案根目錄，列出實際使用的第三方套件及已驗證版本。預計包括 Streamlit、Pandas、Plotly、OpenAI SDK、Pydantic、python-dotenv 與 pytest。SQLite 使用 Python 內建模組，PDF 依實作情況加入 ReportLab。 [Streamlit 依賴設定](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)

## 建立 GitHub Repository

1. 使用者登入 GitHub，建立空白 `CarbonLens` Repository，依課程展示與原始碼分享需求選擇可見性。使用既有本機 Git 專案，建立遠端時讓 README、授權和 `.gitignore` 保持未初始化。 [GitHub 上傳既有本機專案](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
2. 從專案根目錄檢查 `git status --short`、`git remote -v` 及分支名稱。對 `.env`、`.streamlit/secrets.toml`、本機資料庫、匯出報告和真實上傳資料使用忽略規則。示範 CSV 使用合成資料。
3. 加入要發布的程式、文件、合成資料與測試，檢查 `git diff --cached` 後提交。若尚未設定遠端，可依下例設定。推送前用 `git branch --show-current` 確認實際分支，並在 Community Cloud 填入同一名稱。

```powershell
git add -- .gitignore .env.example .streamlit/config.toml README.md development_log.md app.py requirements.txt assets data src tests docs
git diff --cached
git commit -m "Prepare CarbonLens for deployment"
git remote add origin https://github.com/YOUR-ACCOUNT/CarbonLens.git
git remote -v
git push -u origin HEAD
```

## 建立 Streamlit Community Cloud 應用

1. 使用者登入 Streamlit Community Cloud，依平台畫面連接 GitHub 帳號並授權讀取指定 Repository。 [Streamlit 帳號與授權說明](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/create-your-account)
2. 在工作區選 **Create app**，輸入 Repository、已推送的分支及入口 `app.py`。可在 **App URL** 選擇可用的展示子網域。 [Streamlit 部署步驟](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
3. 在 **Advanced settings** 選擇測試過的 Python 版本，在 **Secrets** 貼上 TOML 格式的部署設定。下例欄名是規劃中的 OpenAI 設定，值由帳號持有人在平台填寫。實際設定的欄位清單會隨功能實作更新。 [Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

   ```toml
   OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
   OPENAI_MODEL = "YOUR_STRUCTURED_OUTPUTS_MODEL"
   ```

4. 選 **Deploy** 並檢查啟動紀錄，等待平台分配 `streamlit.app` 網址。確認 **Sharing** 設為公開時，仍應以無痕視窗測試 CarbonLens 的使用權限。 [Streamlit 應用分享與可見性](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)

## 展示權限、API 用量及資料保存

- 公開網址顯示品牌與 Synthetic Data 示範。匿名訪客可以操作標記為 Mock 的合成示範。真實模型、上傳與正式覆核需先通過伺服器端存取檢查。應用保存案例的存取者身分，讀寫均驗證權限。
- 真實模型呼叫設輸入長度、請求逾時、每位授權使用者與整體應用配額。伺服器應在呼叫前檢查配額並防止重複提交。若用量限制僅保存於程序內，程序重啟會重設用量。需跨重啟計數時，使用持久化的共用儲存。
- 本機案件與覆核紀錄可由 SQLite 保存。Community Cloud 展示版採短期儲存並標示保存限制，讓使用者下載報告。需要長期保留案件與覆核時，將儲存介面接到 Supabase PostgreSQL 等外部資料庫，將連線資訊存入 Secrets，並測試重啟後的保存與存取權限。 [Streamlit 本機檔案儲存限制](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)

## 公開網址驗收

1. 在無痕視窗與行動裝置開啟公開網址，確認首頁、繁體中文、品牌、導覽及圖表版面。
2. 選擇三檔示範基金，核對符合、不一致與資料不足的狀態、證據與圖表。資料不足案件的基金 WACI 與實際降低比例應為空。
3. 從未授權工作階段驗證受保護操作會要求存取憑證。使用已授權工作階段建立案例，測試 CSV 格式錯誤與正常上傳，以合成宣稱確認 Real 模式至少一次成功。檢查逾時、額度超限及重複送出時的使用者訊息。
4. 操作確認、修正、退回與重新分析，核對案件版本、覆核意見及來源證據。下載報告並檢查檔名、欄位、中文字元與空數值。若配置了外部資料庫，重啟後重新讀取案件並驗證權限。
5. 保存實際網址、部署日期、Git commit、Python 版本、展示模式及逐項驗證結果。帳號登入、Repository 授權、Secret 輸入與部署操作由具權限的帳號持有人完成。
