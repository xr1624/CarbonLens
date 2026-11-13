# CarbonLens

**See Beyond the Green.**

AI-Powered Carbon Claim Verification Platform

基於 AI Agent 之永續基金低碳宣稱與碳排表現一致性分析系統  
CarbonLens: An AI Agent-Based Carbon Claim Verification System for Sustainable Investment Funds

CarbonLens 是「永續投資與綠色金融創新」課程的概念驗證。研究分析師可用它核對基金原文、持股加權平均碳強度（WACI）與市場基準，留下可追溯的證據與覆核紀錄。結果供漂綠風險初步篩選使用，法律與廣告認定超出系統的分析範圍。

## 專案文件

| 文件 | 閱讀內容 |
| --- | --- |
| [系統架構](docs/architecture.md) | 模組分工、預計的資料夾結構、使用者操作與開發順序 |
| [資料設計](docs/data_design.md) | 三份 CSV 的欄位、檢核規則、WACI、覆蓋率與示範基金的預期值 |
| [Agent 工作流程](docs/agent_workflow.md) | 資料來源、AI 擷取、工具分支、確定性計算與人工覆核的流程圖 |
| [測試與驗收計畫](docs/testing.md) | 獨立案例、真實模型驗收、評估方式與結果紀錄 |
| [公開部署計畫](docs/deployment.md) | GitHub、Streamlit Community Cloud、Secrets、存取與儲存策略 |
| [開發紀錄](development_log.md) | 本次實際完成的工作、檢查與開發決策 |
| [V2.3 公開驗收清單](docs/assignment_checklist.md) | 任務四的公開 HTTPS 操作、AI、覆核、下載及安全驗收 |
| [任務五評估紀錄](docs/task5_evaluation.md) | 部署前檢查與後續公開網站實測結果 |

已整合模型工具呼叫、WACI、授權登入、覆核與報告下載。GitHub 專案為 https://github.com/xr1624/CarbonLens ，部署分支為 `codex/deploy`。公開網址與真實模型成功驗證仍待完成，測試狀態見任務五紀錄。

## 本機啟動與測試

在專案目錄使用 Python 3.11 以上版本安裝依賴並執行測試。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

開啟 [CarbonLens 本機網站](http://localhost:8501/)。在另一個終端機執行測試。

```powershell
.venv\Scripts\python.exe -m pytest -q
```

若 `python --version` 無法執行，請先讓終端機使用可執行的 Python 3.11 以上版本，再建立虛擬環境。本階段實測使用 Codex 隨附的 Python 3.12.14。

`data/` 內三份 CSV 都是 Synthetic Data。`load_csv` 先檢查欄名與列格式並保留來源列號，再建立 Pandas DataFrame。`validate_portfolio` 驗證指定基金，回傳資料問題與權重覆蓋率。`analyze_portfolio` 接收驗證結果與可從原文核對的宣稱門檻，計算 WACI、實際降低比例及持股貢獻。第三檔基金缺碳強度，僅回傳 60% 覆蓋率及資料不足的判定。

以下用原文中的 30% 手動指定門檻。若宣稱待確認，傳入 `None`。

```python
from decimal import Decimal
from pathlib import Path

from src.calculations import analyze_portfolio
from src.validation import load_csv, validate_portfolio

funds = load_csv(Path("data/funds.csv"), "funds")
holdings = load_csv(Path("data/holdings.csv"), "holdings")
benchmarks = load_csv(Path("data/benchmarks.csv"), "benchmarks")
validation = validate_portfolio(funds, holdings, benchmarks, "SYN001")
result = analyze_portfolio(validation, Decimal("30"))
print(result.status.value, result.fund_waci, result.actual_reduction_pct)
```

## 在瀏覽器操作

1. 到「建立案件」，選擇 Synthetic Data 和基金 `SYN001`。依原文填入 30、勾選確認並按「建立案件並分析」。
2. 應顯示基金 WACI 50、基準 WACI 100、實際降低 50%，並產生四張互動圖。展開「證據來源與計算公式」可核對資料列。
3. 以相同步驟驗證 `SYN002` 與 `SYN003`，或改選「上傳 CSV」上傳 `data/` 內的三份資料。缺少必要欄位的檔案會顯示檔名及問題。若宣稱待確認，保留原文並將降低比例留空。
4. 切回「分析總覽」查看累計案件，在「案件分析」選擇已建立案件。案件保存在目前 Streamlit 工作階段，重新整理或重新啟動可能清除案件。

亦可選擇 Mock Mode 示範擷取，或登入後以 Real 呼叫模型。操作步驟見 [使用者說明](docs/user_guide.md)。登入案件使用 SQLite 或設定的 PostgreSQL，Cloud 的 SQLite 不保證跨重啟保存。

## 最新本機操作

已整合授權登入、宣稱擷取、覆核與匯出。使用者操作請見 docs/user_guide.md。部署 Secrets 範本在 .streamlit/secrets.example.toml，請勿放入真實金鑰後提交。

本機可使用 .venv/runtime/Scripts/python.exe -m streamlit run app.py。啟用該環境後，也可執行 python -m streamlit run app.py。

目前公開網址仍待部署；真實 AI 遭 API 額度或限流錯誤，尚未通過驗收。
