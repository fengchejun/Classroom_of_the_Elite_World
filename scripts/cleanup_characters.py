"""
Clean up characters_extracted.json to May 1st anchor point.
Removes secrets and relationships that develop after Volume 1 "终结的日常".
Characters not yet introduced at May 1st get minimal status.
"""

import json
from pathlib import Path

INPUT = Path(__file__).resolve().parent / "output" / "characters_extracted.json"
OUTPUT = INPUT  # Overwrite in place (backup already made)

# ============================================================
# May 1st anchor rules:
# - Only relationships formed by the END of Volume 1's "终结的日常"
# - White Room background: ONLY 绫小路 himself knows
# - 栉田 dark side: ONLY 栉田 herself knows
# - 軽井沢 past trauma: ONLY 軽井沢 herself knows at this point
# - 平田 trauma: NO ONE knows
# - 龙园's grip on C班: just beginning, only C班 students affected
# - 坂柳, 南云, 月城, 宝泉, 八神, 天泽, 桐山, 桥本, 鬼头 etc.: NOT YET INTRODUCED
# - 佐仓爱里: barely interacted with
# ============================================================

# Characters who have NOT YET appeared or have zero presence at May 1st
# Their data should be minimal
NOT_YET_INTRODUCED = {
    "南云雅", "桐山生", "宝泉和臣", "八神拓也", "天泽一夏",
    "月城", "月城代理理事长", "桥本正义", "鬼头隼",
    "坂柳有栖",  # technically exists but not active
    "神室真澄",  # 坂柳's follower, not active
    "山村美纪",
    "西野武子",
    "松雄",
    "绫小路笃臣",  # never at school
    "司马克典",
    "椿樱子",
    "宇都宫", "石", "石上京", "石仓", "石井",
    "真田", "高原", "高桥", "高桥修",
    "时任裕也",
    "渡边", "渡边正义",
    "町田", "町田浩二",
    "滨口", "滨田",
    "长谷部", "长谷川",
    "金田", "野村", "野村雄二",
    "铃木", "铃木园",
    "阿部", "阿部隆",
    "青山", "青木",
    "饭岛", "饭田",
    "黑木", "黑田",
    "近藤", "近藤玲奈",
    "柴田", "柴田飒",
    "木下", "木下美香",
    "本堂", "本堂辽",
    "安藤", "安藤纱耶",
    "小田", "小田真理",
    "小宫", "小宫地",
    "小栗", "小栗旬",
    "小桥", "小桥美咲",
    "小林", "小林正人",
    "山下", "山下健太",
    "山田", "山田阿尔伯特",
    "山田阿尔伯特",
    "川上", "川上沙纪",
    "平贺", "平贺源二",
    "幸村", "幸村辉彦",
    "户冢", "户冢弥彦",
    "星之宫", "星之宫知惠",
    "星之宫知惠",
    "春田", "春田美咲",
    "朝比奈", "朝比奈荠",
    "朝比奈なずな",
    "本多", "本多美代",
    "朱鹭", "朱鹭田",
    "松下", "松下千秋",
    "松下千秋",
    "栉田",  # duplicate of 栉田桔梗
    "椎名", "椎名日和",
    "橘", "橘茜",
    "水上", "水上知里",
    "水木", "水木秀",
    "永井", "永井健",
    "池", "池田",
    "沢田", "沢村",
    "河西", "河合",
    "波多野", "波田野",
    "泽田", "泽村",
    # keep checking: characters whose role is only in later arcs
}

# Per-character: secrets and relations valid at May 1st
# For characters not listed here, we KEEP their data but remove obviously
# post-May-1st relations (those mentioning midterm, island, boat, sports festival, etc.)

# Keywords that indicate a secret/relation belongs to POST-May-1st timeline
POST_ANCHOR_KEYWORDS = [
    "无人岛", "期中", "期末", "体育祭", "船上", "Paper Shuffle",
    "合宿", "圣诞节", "圣诞", "新年", "情人节",
    "二年级", "三年级", "修学旅行", "文化祭",
    "White Room", "white_room", "白屋", "白屋",
    "WhiteRoom",
    "学生会", "会长",  # 堀北学相关 is May 1st OK, but 学生会 involvement is borderline
    "南云", "坂柳",
    "退学",  # 退学 threats happen later
    "龙园",  # direct mention of 龙园 in non-C-class relations is post-May-1st
    "一之濑",  # crossing class lines
    "姫野", "椎名",
]

# Specific relations to remove (based on character names and target)
# Format: (from_name, to_name_substring)
REMOVE_SPECIFIC_RELATIONS = [
    # 绫小路 - remove all post-May1st relations
    ("绫小路清隆", "佐仓"),("绫小路清隆", "佐藤"),
    ("绫小路清隆", "轻井泽"), ("绫小路清隆", "軽井沢"),
    ("绫小路清隆", "龙园"),
    ("绫小路清隆", "一之濑"), ("绫小路清隆", "一之瀬"),
    ("绫小路清隆", "坂柳"),
    ("绫小路清隆", "伊吹"),
    ("绫小路清隆", "葛城"),
    ("绫小路清隆", "南云"),
    ("绫小路清隆", "月城"),
    ("绫小路清隆", "天泽"),
    ("绫小路清隆", "宝泉"),
    ("绫小路清隆", "桐山"),
    ("绫小路清隆", "桥本"),
    ("绫小路清隆", "八神"),
    ("绫小路清隆", "外村"),
    ("绫小路清隆", "三宅"),
    ("绫小路清隆", "鬼头"),
    ("绫小路清隆", "绫小路笃臣"),
    ("绫小路清隆", "堀北学"),  # 学生会邀请 happens later
    ("绫小路清隆", "坂柳有栖"),
    # 堀北铃音
    ("堀北铃音", "栉田"),  # 堀北 doesn't interact with 栉田 much yet
    # Remove relations mentioning later events
]

# Secrets to remove (info_id contains these)
REMOVE_SECRETS_KEYWORDS = [
    "white_room", "白屋", "White Room", "WR",
    "ayanokoji_past",  # 茶柱 doesn't know this yet
    "father",
    "bully", "trauma", "past",  # Most trauma is unknown at May 1st
    "karuizawa",  # 軽井沢 secrets unknown
    "hirata",  # 平田 secrets unknown
    "kushida_dark",  # Only 栉田 herself knows
    "ryuen_rule",  # 龙园 control just starting
]

# Known-by lists: at May 1st, secrets should only be known_by the character themselves
# unless explicitly shared in the first month
ONLY_SELF_KNOWS = {
    "ayanokoji_true_nature", "hidden_ability", "horikita_brother_complex",
    "kushida_dark_side", "hirata_trauma", "karuizawa_past",
    "sudo_potential", "ryuen_rule_c", "ichinose_past",
}


def should_remove_relation(char_name: str, rel: dict) -> bool:
    """Check if a relation should be removed based on post-May-1st timeline."""
    target = rel.get("to", "")
    reason = rel.get("reason", "")
    rel_type = rel.get("type", "")

    # Check specific removal list
    for from_name, to_substr in REMOVE_SPECIFIC_RELATIONS:
        if from_name == char_name and to_substr in target:
            return True

    # Check keywords in reason
    for kw in POST_ANCHOR_KEYWORDS:
        if kw in reason or kw in target:
            return True

    # "退学" in reason is usually post-May-1st
    if "退学" in reason:
        return True

    # Relations with characters not yet introduced
    if target in NOT_YET_INTRODUCED:
        return True

    # "交往" / "女朋友" / "男朋友" - romantic relationships don't exist yet
    if any(w in reason for w in ["交往", "女朋友", "男朋友", "约会", "告白"]):
        return True

    # "crush" type relations are all later
    if rel_type == "crush":
        return True

    return False


def should_remove_secret(secret: dict) -> bool:
    """Check if a secret should be removed."""
    info_id = secret.get("info_id", "")
    content = secret.get("content", "")
    known_by = secret.get("known_by", [])

    # Check info_id keywords
    for kw in REMOVE_SECRETS_KEYWORDS:
        if kw.lower() in info_id.lower() or kw.lower() in content.lower():
            return True

    # At May 1st, secrets should only be known by the character themselves
    # unless it's public knowledge
    if info_id in ONLY_SELF_KNOWS:
        if len(known_by) > 1 or (known_by and known_by[0] != info_id.split("_")[0]):
            return True

    # "期中考" / "无人岛" / "学生会" mentions
    for kw in ["期中", "无人岛", "体育祭", "船上", "合宿", "Paper Shuffle"]:
        if kw in content:
            return True

    return False


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    chars = data["data"]
    removed_relations = 0
    removed_secrets = 0
    total_relations_before = 0
    total_secrets_before = 0

    for char in chars:
        name = char.get("name", "")
        old_rels = char.get("relations", [])
        old_secs = char.get("secrets", [])
        total_relations_before += len(old_rels)
        total_secrets_before += len(old_secs)

        # Filter relations
        new_rels = []
        for rel in old_rels:
            if not should_remove_relation(name, rel):
                new_rels.append(rel)
        removed_relations += len(old_rels) - len(new_rels)
        char["relations"] = new_rels

        # Filter secrets
        new_secs = []
        for sec in old_secs:
            if not should_remove_secret(sec):
                # Also sanitize known_by: at May 1st, most secrets are self-known only
                # Only keep known_by entries for public or early-revealed info
                info_id = sec.get("info_id", "")
                content = sec.get("content", "")
                # If it's a secret, at May 1st only the character themself knows it
                if "secret" in info_id.lower() or "secret" in content.lower() or \
                   any(kw in content for kw in ["秘密", "真面目", "真实", "隐藏"]):
                    # Keep only self in known_by (convert role_id to self)
                    sec["known_by"] = [char.get("role_id", "")]
            new_secs.append(sec)
        removed_secrets += len(old_secs) - len(new_secs)
        char["secrets"] = new_secs

        # Clean up traits: remove duplicates and normalize
        seen = set()
        clean_traits = []
        for t in char.get("traits", []):
            t = t.replace("主义者", "主义").replace("的", "").strip()
            if t not in seen and len(t) <= 8:
                seen.add(t)
                clean_traits.append(t)
        char["traits"] = clean_traits[:8]  # Max 8 traits

    # Deduplicate relations (same to + same type)
    for char in chars:
        seen = set()
        unique_rels = []
        for rel in char.get("relations", []):
            key = (rel.get("to", ""), rel.get("type", ""))
            if key not in seen:
                seen.add(key)
                unique_rels.append(rel)
        char["relations"] = unique_rels

    # Remove characters who are NOT YET INTRODUCED and have no meaningful data
    filtered_chars = []
    for char in chars:
        name = char.get("name", "")
        if name in NOT_YET_INTRODUCED:
            if len(char.get("relations", [])) == 0 and len(char.get("secrets", [])) == 0:
                # Keep as placeholder with minimal info
                char["status_at_anchor"] = "未登场"
                char["public_info"] = [{"label": "状态", "content": "5月1日时尚未登场或未活跃"}]
        filtered_chars.append(char)

    # Report
    total_relations_after = sum(len(c.get("relations", [])) for c in filtered_chars)
    total_secrets_after = sum(len(c.get("secrets", [])) for c in filtered_chars)

    print(f"Characters: {len(filtered_chars)}")
    print(f"Relations: {total_relations_before} -> {total_relations_after} (removed {removed_relations})")
    print(f"Secrets: {total_secrets_before} -> {total_secrets_after} (removed {removed_secrets})")

    # Save
    output = {"type": "characters", "data": filtered_chars}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved cleaned data to: {OUTPUT}")


if __name__ == "__main__":
    main()
