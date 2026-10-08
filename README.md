<p align="center">
  <img src="assets/degree-savior-banner.png" alt="Degree Savior — 從研究想法到可檢查的證據" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square" alt="Python 3.10 or newer">
  <img src="https://img.shields.io/badge/Codex%20CLI-0.160.1-111827?style=flat-square" alt="Codex CLI 0.160.1 tested">
  <img src="https://img.shields.io/badge/Discord-English%20embeds-5865F2?style=flat-square" alt="English Discord embeds">
  <br>
  <img src="https://img.shields.io/badge/pypdf-6.19.0-2563EB?style=flat-square" alt="pypdf 6.19.0">
  <img src="https://img.shields.io/badge/ReportLab-5.0.1-DC2626?style=flat-square" alt="ReportLab 5.0.1">
  <img src="https://img.shields.io/badge/SQLite-local%20state-0D9488?style=flat-square" alt="Local SQLite state">
</p>

# Degree Savior

**把研究想法，推進到能核對的論文證據與實驗結果。** Degree Savior 搜尋相關工作、保存全文與研讀筆記、整理可能的研究缺口。你選定題目後，它接著提出假設、實作實驗、量測與分析，並透過 Discord 傳送英文摘要與 PDF 報告。

你負責提出問題與選擇方向。**文獻調查與實驗之間有一道人工選題關卡**：沒有你對目前題目版本的明確批准，就不會開始規劃或執行實驗。批准後，規劃自動接上實驗，成功、負面與無法判定的結果都會保留。

## 從想法接續到研究結果

### 查清楚相關工作，再評估研究缺口

在對話中提出想法，或指定想探索的領域與限制。系統透過 OpenAlex、Crossref 與 arXiv 查找論文，追蹤引用，核對書目，下載可取得的全文。每篇作為證據的論文都有 PDF、研讀筆記與頁面引用，綜述比較方法、假設、實驗、已有結果及限制。

工作區可設定只接受已核對的主要 conference／journal 正式發表作為硬證據，其餘來源列為補充。出版身分與全文研讀分別驗證；只有標題、摘要或搜尋結果，不能冒充讀過全文。已有工作涵蓋想法時，最多再深入探索兩輪改進。

研究缺口限於記錄的搜尋範圍與日期。接近的工作拿不到全文、證據不符或調查不完整時，報告會明示限制；搜尋沒有找到，不等於證明從未有人做過。

### 你選題後，才開始假設與實驗

可選題目會各自收到一份英文 PDF 與一則 Discord Embed，包含問題、相關工作、有界缺口、限制及目前版本。你可以在對話中批准、要求修改、暫緩或拒絕；沉默與通知送達不會被當成同意。

批准後，系統凍結假設、程式、資料、主要指標、基準、消融、種子、成功標準及資源預算，再自動接續執行。一般規劃與實驗不逐項重問；題目或關鍵證據改變、原批准失效或資源不足時，會保存原因。

### 實際量測，也留下沒有成功的結果

目前支援本機 Python 計算實驗，以成對的獨立執行單位比較候選方法、基準與消融。流程包括正確性檢查、開發用試跑、正式量測、成對 Bootstrap、多重比較修正、另開程序重現、原始資料重算與科學證據審查。

程式成功結束不代表假設成立。報告區分 `SUPPORTED`、`NOT_SUPPORTED`、`INCONCLUSIVE`、`INVALID`、`BLOCKED` 與 `CANCELLED`，保留所有計畫中的假設與執行紀錄。科學審查仍可能有判斷限制；研究結果必須連同原始證據與適用範圍閱讀。

## 在 Discord 閱讀，研究紀錄留在本機

Discord 只傳值得閱讀或需要決定的內容：已驗證的論文研讀、文獻／主題統整、選題、實驗結論、完整報告與實質研究阻礙。**Embed 和 PDF 使用英文，保留技術術語。** 論文名稱、來源與出版日期在最上方，識別碼放在標題旁括號；一般開始、完成、排隊、下載、儲存及系統維護不洗頻。

背景程序保存通知與送達紀錄，有限重試暫時性失敗；網路逾時仍可能重送。PDF 附件有本機大小上限，較大的原始證據留在本機。Webhook 提供通知出口，選題由對話介面記錄，沒有 Discord 入站批准功能。

| 本機位置 | 保存內容 |
| --- | --- |
| `ideas/`、`topic/` | 原始想法、搜尋、綜述、題目版本與選題狀態 |
| `papers/` | 論文 PDF、筆記與研讀報告 |
| `hypothesis/`、`local/` | 題目專屬規格、假設與凍結計畫 |
| `experiments/` | 每個批次的程式、輸入、檢查點、量測與分析 |
| `results/` | 完整結果、PDF、統計表與重現資料 |
| `state/` | 佇列、決策、檢查點及通知收據 |

以上研究目錄、`.env` 和本機設定都由 Git 忽略。公開專案保留程式、通用文件、測試與資源；個人的研究內容不放進共享系統文件。

## 讓 coding agent 設定，之後直接在對話中使用

需要 Python 3.10+ 與已登入的 Codex CLI；推理沿用本機登入，專案沒有固定模型名稱。Discord Webhook 和 OpenAlex Key 由本機隱藏輸入或忽略的 `.env` 設定，不需要貼進聊天。Key 是否必要取決於來源當時的存取要求；不能把一次成功查詢當成永久可用。

預設一次跑一個實驗，每次最多 300 秒、4 GiB RAM，整批最多 150 次與兩小時；不配置付費計算。已批准批次可以記錄明確的時間延長。選用的 NumPy／PyTorch 支援 CPU 神經實驗，程式仍受依賴與執行限制；GPU 記憶體沒有獨立監控。

背景程序啟動後能跨聊天回合接續，電腦需保持開機、連網且不睡眠。停止或更新時保留證據與紀錄，恢復先核對檔案與程序；同一工作區只允許一個 worker。目前不安裝開機自動啟動排程。

## 複製這段訊息給你的 coding agent

```
Read [AGENTS.md](AGENTS.md), the [installation guide](docs/installation-guide.md), [system plan](docs/plan.md) and [verification record](docs/verification.md). Follow the guide to inspect or reuse the environment, check Codex authentication, configure missing credentials through local hidden input, validate the application, and start exactly one worker. Keep executable commands in the guide.

Connect research requests to the installed CLI. Inspect actual topic, survey and paper artifacts before reporting findings. Approve a topic only after the user explicitly selects its exact current revision; preserve the original instruction and authorized limits. Approval automatically queues planning and experiments. A notification, recommendation or elapsed time never grants approval.

Use English embeds and PDF research reports under the notification allowlist. Let the worker send its queued messages and inspect receipts; avoid duplicate manual sends. Keep maintenance and lifecycle events local. Preserve papers, decisions, measurements and notification history during recovery, and distinguish application tests from scientific findings.

Keep topic-specific instructions and research in ignored local directories. Before any user-authorized Git publication, inspect the complete proposed tree for credentials, personal filesystem paths and research artifacts. Publish only generic application files; do not delete local research to make the repository clean.
```
