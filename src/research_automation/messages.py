"""Traditional Chinese Discord embeds; technical identifiers stay literal."""
import json
import re

TITLES = {
    "system.initialized": "研究自動化系統已初始化", "idea.accepted": "已接收研究想法",
    "job.queued": "工作已排入佇列", "job.started": "工作開始", "job.done": "工作完成",
    "job.blocked": "工作暫時受阻", "job.cancelled": "工作已取消", "job.resumed": "工作已恢復",
    "job.recovered": "已恢復中斷的工作", "job.progress": "工作進度更新",
    "agent.started": "研究分析開始", "agent.completed": "研究分析完成", "agent.reused": "已沿用驗證過的分析",
    "artifact.saved": "研究檔案已儲存", "implementation.file_completed": "系統檔案已完成",
    "artifact.publication_recovered": "已恢復主題檔案與狀態紀錄",
    "implementation.file_ready": "實驗程式已準備完成", "implementation.started": "開始建置研究系統",
    "literature.query_started": "文獻搜尋開始", "literature.query_completed": "文獻搜尋完成", "literature.query_failed": "文獻搜尋失敗",
    "literature.citation_trace_started": "引文追蹤開始", "literature.citation_trace_completed": "引文追蹤完成",
    "paper.screened": "論文篩選完成", "paper.download_started": "開始下載論文", "paper.download_failed": "論文下載失敗",
    "paper.pdf_validated": "論文 PDF 已驗證", "paper.note_saved": "論文研讀筆記已儲存", "paper.reused": "已沿用驗證過的論文與筆記", "paper.evidence_blocked": "論文證據不足",
    "topic.assessed": "研究主題評估完成", "topic.refinement_started": "開始深入探索改進方向", "topic.awaiting_selection": "研究主題待您選擇", "topic.review_closed": "文獻審查已結束",
    "selection.approved": "已確認您選擇的研究主題", "selection.reject": "研究主題已拒絕", "selection.defer": "研究主題已暫緩", "selection.revise": "研究主題將重新審查", "selection.cancel": "研究工作已取消", "selection.stale_rejected": "主題版本已變更，請重新選擇",
    "hypothesis.plan_ready": "研究假設與驗證計畫已完成", "planning.completed": "計畫完成，將自動執行實驗",
    "planning.validation_failed": "驗證計畫需要修正",
    "experiment.run_started": "實驗執行開始", "experiment.run_completed": "實驗執行完成", "experiment.run_reused": "已沿用完成的實驗", "experiment.run_interrupted": "實驗執行已中斷", "experiment.run_failed": "實驗執行失敗", "experiment.run_invalid": "實驗量測無效", "experiment.run_recovered_completed": "已恢復完成的實驗紀錄",
    "hypothesis.verified": "研究假設驗證完成", "hypothesis.outcome_saved": "研究假設結果已儲存", "campaign.result": "完整研究結果已儲存",
    "workflow.blocked": "研究流程暫時受阻", "worker.started": "背景工作程序已啟動", "worker.stopped": "背景工作程序已停止", "worker.stop_requested": "已要求停止背景工作程序", "interface.action_completed": "工作完成通知",
}
VALUES = {
    "review": "文獻審查", "plan": "假設規劃", "execute": "實驗執行", "backward": "參考文獻追蹤", "forward": "後續引用追蹤",
    "closest": "最接近的相關研究", "relevant": "相關研究", "excluded": "排除",
    "CANDIDATE": "可選研究主題", "COVERED": "已有研究涵蓋", "UNRESOLVED": "尚無法確認", "EVIDENCE_BLOCKED": "關鍵證據不足", "AWAITING_SELECTION": "等待您的選擇",
    "SUPPORTED": "假設獲得支持", "NOT_SUPPORTED": "假設未獲支持", "INCONCLUSIVE": "證據尚不充分", "INVALID": "量測或設計無效", "BLOCKED": "工作受阻", "CANCELLED": "已取消", "COMPLETED": "已完成", "PARTIAL": "部分完成",
    "correctness": "正確性檢查", "smoke": "基本執行檢查", "confirmation": "正式驗證", "reproduction": "重現驗證",
    "timeout": "超過時間限制", "memory_limit": "超過記憶體限制", "output_limit": "超過輸出大小限制", "owner_interrupted": "背景工作程序中斷",
    "mean": "平均值", "lower": "區間下界", "upper": "區間上界", "n": "樣本數", "outcome": "結論", "supported": "通過支持標準", "baseline_improvement": "相對基準的改善", "ablation_improvement": "相對消融方法的改善",
}
FIELDS = {
    "entity": "工作識別碼", "topic": "研究主題", "topic_id": "研究主題", "revision": "主題版本", "provided_revision": "選擇的版本", "current_revision": "目前版本", "campaign": "研究批次", "job": "工作編號", "paper": "論文編號", "hypothesis": "假設編號", "run": "實驗編號", "phase": "工作階段", "stage": "實驗階段", "provider": "文獻來源", "query": "搜尋條件", "direction": "追蹤方向", "relevance": "相關程度", "decision": "評估結論", "outcome": "驗證結論", "status": "狀態", "count": "數量", "pages": "PDF 頁數", "round": "深入探索輪次", "elapsed_seconds": "已用秒數", "outcomes": "各類結果數量", "statistics": "量測與統計結果", "findings": "研究發現", "question": "研究問題", "gap": "可能的研究缺口", "feasibility": "可行性", "limitations": "限制與注意事項", "reason": "原因", "error": "錯誤資訊", "artifact": "研究檔案", "path": "檔案路徑", "result": "完整結果檔案", "source": "來源", "closest_papers": "最接近的論文", "approval": "選擇紀錄", "audit_pass": "詳細證據檢查通過", "sha256": "檔案指紋", "producer": "產生此檔案的工作",
}
NATURAL = {"question", "gap", "feasibility", "limitations", "reason", "error"}


def units(text):
    return len(text.encode("utf-16-le")) // 2


def chunks(text, limit):
    current = ""
    for character in text:
        if units(current + character) > limit:
            yield current
            current = ""
        current += character
    if current:
        yield current


def translated(value):
    if isinstance(value, dict):
        return {VALUES.get(k, FIELDS.get(k, k)): translated(v) for k, v in value.items()}
    if isinstance(value, list):
        return [translated(v) for v in value]
    if isinstance(value, str):
        return VALUES.get(value, value)
    if isinstance(value, bool):
        return "是" if value else "否"
    return value


def human_text(value):
    value = str(value)
    if re.search(r"[\u3400-\u9fff]", value):
        return value
    translations = {
        "Source connection failed or timed out": "連線至文獻來源失敗或逾時。",
        "No accessible PDF source was discovered": "尚未找到可取得的論文 PDF。",
        "Source returned a non-PDF response": "下載來源回傳的內容不是 PDF。",
        "PDF bibliographic identity does not match the discovered paper": "下載的 PDF 與論文書目資訊不相符。",
        "Paper requires OCR or has insufficient readable text": "論文需要 OCR，或可讀文字不足。",
        "Campaign elapsed-time budget exhausted": "研究批次已達時間上限。",
        "Phase elapsed-time budget exhausted": "目前階段已達時間上限。",
        "User revoked or cancelled work": "您已撤回選擇或取消研究工作。",
        "Campaign stopped before this hypothesis could be evaluated": "研究批次已停止，此假設尚未完成驗證。",
    }
    if value in translations:
        return translations[value]
    if "budget exhausted" in value.lower():
        return "已達預先設定的資源或執行次數上限；詳細項目請見本機事件紀錄。"
    match = re.search(r"HTTP (\d+)", value)
    if match:
        return "來源伺服器回覆 HTTP " + match.group(1) + "；詳細資訊請見本機事件紀錄。"
    return "詳細內容請見對應的本機研究檔案或事件紀錄。"


def build_messages(action, data, event_id, sequence, created):
    title = TITLES.get(action, "研究工作通知")
    description = title + "。"
    summary = data.get("summary", "")
    if isinstance(summary, str) and (re.search(r"[\u3400-\u9fff]", summary) or (summary and not summary.isascii())):
        description = summary
    if action == "topic.awaiting_selection":
        description = "文獻審查已完成，找到可進一步驗證的研究方向。請在目前的對話介面選擇：批准、修改、拒絕或暫緩。您批准前，系統不會規劃假設或開始實驗。"
    elif action == "campaign.result":
        description = "研究結果已完整儲存，包含成功、未獲支持、證據不足及未完成的假設。請依下方結論與檔案路徑查看詳細證據。"
    field_parts = []
    for key, value in data.items():
        if key not in FIELDS or value is None or value == "":
            continue
        text = human_text(value) if key in NATURAL else json.dumps(translated(value), ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(translated(value))
        for i, part in enumerate(chunks(text, 900), 1):
            field_parts.append({"name": FIELDS[key] + (f"（第 {i} 段）" if units(text) > 900 else ""), "value": part, "inline": key not in {"question", "gap", "feasibility", "limitations", "statistics", "findings", "reason", "error"}})
    pages = []
    descriptions = list(chunks(description, 3500)) or [title + "。"]
    for paragraph in descriptions:
        embed = {"title": title, "description": paragraph, "color": 0xE67E22 if any(x in action for x in ("failed", "blocked", "invalid", "interrupted")) else 0x2ECC71 if action in {"campaign.result", "hypothesis.verified"} else 0x3498DB, "timestamp": created, "footer": {"text": f"事件 {event_id} · 序號 {sequence}"}, "fields": []}
        pages.append(embed)
    for field in field_parts:
        embed = pages[-1]
        size = units(embed["title"] + embed["description"] + embed["footer"]["text"]) + sum(units(f["name"] + f["value"]) for f in embed["fields"])
        if len(embed["fields"]) >= 25 or size + units(field["name"] + field["value"]) > 5500:
            embed = {"title": title, "description": "此通知的詳細資訊續頁。", "color": pages[0]["color"], "timestamp": created, "footer": dict(pages[0]["footer"]), "fields": []}
            pages.append(embed)
        embed["fields"].append(field)
    for index, embed in enumerate(pages, 1):
        if len(pages) > 1:
            embed["footer"]["text"] += f" · 第 {index}/{len(pages)} 則"
    payloads = [{"embeds": [embed], "allowed_mentions": {"parse": []}} for embed in pages]
    if action == "campaign.result" and data.get("result"):
        payloads[0]["_attachment"] = data["result"]
    return payloads
