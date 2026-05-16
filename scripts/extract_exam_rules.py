"""
Extract detailed special exam rules from all 34 volumes.
Appends to worldview_extracted.json or outputs a standalone exam_rules_extracted.json.
"""

import json
import re
import time
from pathlib import Path

from openai import OpenAI

NOVEL_BASE = Path(r"C:\Users\FengCheJun\Desktop\爬取小说\我的小说正文")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

DEEPSEEK_API_KEY = "sk-a027465f568346db99147bb047d7a643"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-chat"
LLM_MAX_TOKENS = 8192
LLM_TEMPERATURE = 0.2
RATE_LIMIT_SEC = 2.0
MAX_RETRIES = 3


def call_deepseek(system_prompt: str, user_prompt: str) -> str | None:
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"    API error (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt * 2)
    return None


def extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for start, end in [('{', '}'), ('[', ']')]:
        i = text.find(start)
        j = text.rfind(end)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                pass
    return None


SYSTEM_PROMPT = """你是一个数据提取专家。从《实力至上主义教室》小说中提取每一场**特别考试**的完整、详细规则。

**时间体系**：主角绫小路清隆于2024年4月入学。一年级=2024-04至2025-03，二年级=2025-04至2026-03。

**输出格式**（严格JSON，不要解释，不要markdown）：
{
  "exams": [
    {
      "exam_id": "english_snake_case",
      "name": "考试中文名称",
      "year": 1,
      "occurrence_date": "YYYY-MM-DD",
      "announcement_date": "YYYY-MM-DD",
      "overview": "考试的一句话概括",
      "detailed_rules": [
        "规则1：具体规则内容，包含数字、条件、后果",
        "规则2：...",
        "规则3：..."
      ],
      "scoring_mechanism": "如何计分，分数如何影响班级点数",
      "special_items_or_conditions": "特殊道具、特权、额外条件",
      "penalties": "违规惩罚、退学条件",
      "result": "考试结果（如果已知的话）",
      "key_classes_involved": ["A", "B", "C", "D"]
    }
  ]
}

提取要求：
1. **只提取有明确命名的特别考试**，忽略日常小考
2. detailed_rules 要逐条列出所有操作规则，包含具体数字（点数、人数、天数）
3. scoring_mechanism 说明分数如何转化为班级点数
4. 如果同一考试跨越多卷，提取最完整的信息
5. 日期精确到日（无法推断则精确到月）"""


def get_vols():
    vols = []
    for d in sorted(NOVEL_BASE.iterdir()):
        if d.is_dir():
            vols.append((d.name, d))
    return vols


def read_volume(vol_path: Path) -> str:
    files = sorted(f for f in vol_path.iterdir() if f.suffix.lower() == ".txt")
    parts = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
            parts.append(f"=== {fp.stem} ===\n\n{text}\n")
        except Exception:
            pass
    return "\n".join(parts)


def main():
    vols = get_vols()
    all_exams = {}

    print(f"Processing {len(vols)} volumes for exam rules...")

    for i, (vname, vpath) in enumerate(vols):
        text = read_volume(vpath)
        print(f"\n[{i+1}/{len(vols)}] {vname} ({len(text):,} chars)")

        # Only process volumes that might have exam content
        # Use full text but limit to reasonable size
        extract_text = text[:70000] + "\n...\n" + text[-30000:] if len(text) > 100000 else text

        user_prompt = f"""请从以下小说内容中提取所有特别考试的详细规则：

{extract_text}

请严格按JSON格式输出所有找到的特别考试规则。如果本卷没有特别考试的规则说明，返回空数组。"""

        resp = call_deepseek(SYSTEM_PROMPT, user_prompt)
        if resp:
            parsed = extract_json(resp)
            if parsed:
                exams = parsed.get("exams", [])
                print(f"  Found {len(exams)} exams")
                for exam in exams:
                    eid = exam.get("exam_id", "")
                    if eid and eid not in all_exams:
                        all_exams[eid] = exam
                    elif eid:
                        # Merge: keep more detailed version
                        existing = all_exams[eid]
                        if len(str(exam.get("detailed_rules", []))) > len(str(existing.get("detailed_rules", []))):
                            all_exams[eid] = exam

        time.sleep(RATE_LIMIT_SEC)

    # Merge all exam rules into worldview format
    print(f"\nTotal unique exams extracted: {len(all_exams)}")

    # Build rich exam rules for worldview
    exam_rules_text = []
    for eid, exam in sorted(all_exams.items()):
        entry = f"""
## {exam.get('name', eid)}
- 考试ID：{eid}
- 年级：{exam.get('year', '?')}年级
- 发生时间：{exam.get('occurrence_date', '?')}
- 概述：{exam.get('overview', '')}
- 详细规则：
"""
        for rule in exam.get("detailed_rules", []):
            entry += f"  - {rule}\n"
        entry += f"- 计分机制：{exam.get('scoring_mechanism', '')}\n"
        entry += f"- 特殊条件：{exam.get('special_items_or_conditions', '')}\n"
        entry += f"- 惩罚：{exam.get('penalties', '')}\n"
        entry += f"- 结果：{exam.get('result', '')}\n"
        exam_rules_text.append(entry)

    # Save standalone exam rules file
    output = {
        "type": "exam_rules",
        "count": len(all_exams),
        "exams": all_exams,
        "worldview_text": "\n".join(exam_rules_text),
    }
    path = OUTPUT_DIR / "exam_rules_extracted.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {path} ({path.stat().st_size:,} bytes)")

    # Also update the worldview file to include exam rules
    wv_path = OUTPUT_DIR / "worldview_extracted.json"
    if wv_path.exists():
        wv = json.loads(wv_path.read_text(encoding="utf-8"))
        wv["data"]["special_exam_details"] = "\n".join(exam_rules_text)
        wv_path.write_text(json.dumps(wv, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Updated worldview with exam details")

    # Print summary
    print("\n" + "=" * 60)
    print("Extracted Exam Rules:")
    for eid, exam in sorted(all_exams.items()):
        print(f"  [{exam.get('year','?')}年级] {exam.get('name', eid)} @ {exam.get('occurrence_date', '?')}")
    print(f"\nTotal: {len(all_exams)} exams")
    print("=" * 60)


if __name__ == "__main__":
    main()
