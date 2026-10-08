# Degree Savior：coding agent 安裝與操作指南

本文件供 coding agent 實際設定、操作與維護專案。README 保留產品介紹，指令集中於此。

先閱讀 [AGENTS.md](../AGENTS.md)、[實作規劃](plan.md) 與 [驗證紀錄](verification.md)。以下指令在專案根目錄的 Windows PowerShell 執行；其他作業系統使用對應的虛擬環境 Python 路徑。從其他目錄操作時，可在模組名稱後、子指令之前使用 `--root` 指定工作區。

## 1. 檢查既有環境，保留資料

確認 Python 3.10+ 與 Codex CLI 可用。既有 `.venv`、工作程序、憑證與研究紀錄應沿用，不要刪除資料重新開始。

```powershell
python --version
codex --version
codex login status
```

未登入時，引導使用者在本機完成登入：

```powershell
codex login
```

推理程式沿用本機登入，未固定模型名稱。已驗證的 CLI 版本與連線結果見 [驗證紀錄](verification.md)。

## 2. 安裝與初始化

只有缺少虛擬環境時才建立：

```powershell
python -m venv .venv
```

安裝鎖定版本的依賴並初始化工作區：

```powershell
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e .
.\.venv\Scripts\python.exe -m research_automation init
```

初始化建立 `ideas/`、`papers/`、`topic/`、`hypothesis/`、`experiments/`、`results/` 與 `state/`。更新既有安裝時，先確認正在執行的工作；需要替換程式時，等背景程序停止後再更新、驗證與啟動。

## 3. 在本機設定通知憑證

先檢查設定狀態；輸出只顯示是否已設定，不顯示憑證：

```powershell
.\.venv\Scripts\python.exe -m research_automation doctor
```

已設定時沿用。缺少 Discord Webhook 時，在使用者可操作的互動終端中使用隱藏輸入：

```powershell
.\.venv\Scripts\python.exe -m research_automation configure-secret DISCORD_WEBHOOK_URL
```

OpenAlex API Key 為選填，使用者需要設定時使用：

```powershell
.\.venv\Scripts\python.exe -m research_automation configure-secret OPENALEX_API_KEY
```

不要要求使用者把憑證貼進聊天、當作指令參數，或寫進研究檔案與 Git。非互動環境應引導使用者開啟本機互動終端；不要把隱藏輸入改成可見輸入。上述設定方式將憑證保存於工作區外的使用者目錄。

使用者也可在工作區根目錄的 `.env` 設定 `DISCORD_WEBHOOK_URL` 與 `OPENALEX_API_KEY`；檔案已被 Git 忽略。讀取優先序為「非空的程序環境變數 → 非空的工作區 `.env` → 本機憑證檔案」。空值或沒有值的欄位會沿用下一來源。只讀指定工作區的檔案，支援引號、註解與 UTF-8 BOM，不展開變數，也不將檔案內容匯入子程序環境。修改後重新啟動背景程序，讓文獻搜尋來源套用新 Key；不要在檢查時輸出憑證值。

解析採用 [python-dotenv](https://pypi.org/project/python-dotenv/) 的 `dotenv_values`；OpenAlex Key 透過 [官方支援的 Bearer header](https://help.openalex.org/api/authentication/) 傳送，不放入查詢網址。

如需調整限制，可在沒有 `research.json` 時複製 [research.example.json](../research.example.json)，再依使用者授權設定。不要覆寫既有設定。預設每次實驗最多 300 秒、4 GiB 記憶體，整批最多 150 次與 2 小時，不建立付費雲端計算。

## 4. 驗證與啟動背景程序

新安裝或更新程式後，執行依賴檢查與專案測試：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m research_automation doctor
```

確認 Codex 可用且已登入、Discord 已設定，再啟動並查詢狀態：

```powershell
.\.venv\Scripts\python.exe -m research_automation start
.\.venv\Scripts\python.exe -m research_automation status
```

同一工作區只允許一個背景程序；已有程序時沿用。需要診斷時查看 `state/worker.stdout.log` 與 `state/worker.stderr.log`，對外回報前遮罩憑證。

安裝驗證使用合成測試，不要建立或批准真實研究題目來測試。核對背景程序的實際運行狀態與通知送達後，以繁體中文說明哪些功能已確認、哪些仍需要使用者處理。持續運行需保持開機、連網且不睡眠；目前沒有安裝開機啟動排程，重新開機後需再次啟動。

## 5. 將對話中的想法接到研究佇列

使用者提出研究想法時，提交其實際問題：

```powershell
.\.venv\Scripts\python.exe -m research_automation submit "使用者提出的研究想法"
```

使用者要求探索方向時，使用探索模式：

```powershell
.\.venv\Scripts\python.exe -m research_automation submit "研究領域、興趣與資源限制" --discover
```

已確認論文名稱或需要精確補查時，可指定兩個第一輪查詢；系統會保存並原樣使用，不讓模型改寫查詢。後續已涵蓋問題的深入輪次仍產生新查詢，且全文證據與選題批准要求不變。

```powershell
.\.venv\Scripts\python.exe -m research_automation submit "研究問題與已知先例" --discover --query "Discovering Mathematical Equations with Diffusion Language Model" --query "Gene Editing for Symbolic Regression"
```

背景程序會自動調查文獻並停在人工選題。回覆使用者前，讀取實際的主題檔案、文獻綜述與論文筆記，說明研究缺口、搜尋限制與可行性。

## 6. 記錄使用者選題，才接續規劃與實驗

**只有使用者明確選定目前版本的主題，才可執行批准。** 保留使用者原始批准指示，不要用模型判斷、通知送達、沉默或安裝授權代替選題。選擇不明確時，先釐清。

```powershell
$topicId = "實際主題 ID"
$revision = "核對後的目前版本"
$userInstruction = "使用者原始批准指示"
.\.venv\Scripts\python.exe -m research_automation approve $topicId --revision $revision --instruction $userInstruction
```

批准自動接續假設規劃與實驗，不另加一般執行批准關卡。資源變更必須有使用者明確授權；以 `approve` 的 `--limits` JSON 參數記錄批次限制。變更證據、問題範圍或批准失效時，不能沿用舊批准。

其他決定依使用者要求選擇一項執行，不要依序執行整段：

```powershell
.\.venv\Scripts\python.exe -m research_automation revise $topicId "使用者要求重新調查的問題"
.\.venv\Scripts\python.exe -m research_automation defer $topicId "使用者暫緩指示"
.\.venv\Scripts\python.exe -m research_automation reject $topicId "使用者拒絕指示"
.\.venv\Scripts\python.exe -m research_automation cancel $topicId "使用者停止研究的指示"
```

## 7. 停止、恢復與查看紀錄

背景程序的停止會等待目前工作結束；中斷指定研究則使用上一節的 `cancel`：

```powershell
.\.venv\Scripts\python.exe -m research_automation stop
.\.venv\Scripts\python.exe -m research_automation status
```

修復受阻原因、核對有效批准與檔案後，使用實際工作 ID 恢復，再確認背景程序運行：

```powershell
$jobId = "實際受阻工作 ID"
.\.venv\Scripts\python.exe -m research_automation resume $jobId
.\.venv\Scripts\python.exe -m research_automation start
```

需要前景處理目前佇列時，先確認背景程序已停止，再執行；遇到人工選題會自然停下：

```powershell
.\.venv\Scripts\python.exe -m research_automation worker --drain
```

查詢研究事件與通知送達紀錄：

```powershell
.\.venv\Scripts\python.exe -m research_automation events --limit 30
.\.venv\Scripts\python.exe -m research_automation notifications
```

保留論文、決策、凍結計畫、每次實驗與通知紀錄。恢復不能繞過失效批准，也不要為取得正面結論而重跑有效負面結果。

## 8. Discord 通知與故障處理

系統已自動記錄並發送研究事件，agent 不要重複發送相同研究動作。需要留下額外的本機介面紀錄時，可使用繁體中文摘要；依目前偏好，此類紀錄不送 Discord：

```powershell
.\.venv\Scripts\python.exe -m research_automation notify "已完成的操作、驗證結果與需要使用者處理的事項"
```

Discord 只傳研究相關事件，使用繁體中文 Embed。系統設定、程式／文件修改、一般介面完成與背景程序啟停只保留本機事件，不發送通知。上面的 `notify` 記錄一般介面完成事件，依目前偏好不送 Discord；研究事件應由工作流程記錄，避免重複。完成研究的通知包含各假設結論、統計摘要與結果位置，1 MiB 以內的 Markdown 報告可附加傳送。

單篇論文通過全文與原文證據檢查後，`paper.note_saved` 通知「論文分析完成」，包含主要發現、限制與 PDF 研讀報告。一般 agent 分析結束仍靜音。依使用者要求製作的研究進度報告使用 `literature.report`，附 PDF，並明示目前是否仍待查核；不要用 `campaign.result` 冒充已完成實驗。

PDF 使用 ReportLab 5.0.1；Windows 內嵌本機微軟正黑體。其他平台使用標準繁體中文 CID 字型，需要 PDF 閱讀器提供對應字型。PDF 與 Markdown 附件都受本機 1 MiB 上限約束，摘要仍使用中文 Embed。

背景程序會自動處理待送通知；先查紀錄、修復網路或憑證問題。需要手動清空待送通知或重試失敗通知時，先確認背景程序已停止，避免多個發送程序同時操作。依問題選擇一項：

```powershell
.\.venv\Scripts\python.exe -m research_automation notifications --flush
.\.venv\Scripts\python.exe -m research_automation notifications --replay
```

再檢查送達狀態並啟動背景程序。遵循 Discord 速率限制；網路逾時可能造成重送，以事件 ID 辨識。通知失敗不會授權選題或改變研究結論。
