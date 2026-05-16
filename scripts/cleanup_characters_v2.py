"""
Manual cleanup: define exact secrets & relations per key character at May 1st.
Anchor: end of Volume 1 "终结的日常", D班 points just zeroed.
"""

import json
from pathlib import Path

INPUT = Path(__file__).resolve().parent / "output" / "characters_extracted.json"
OUTPUT = INPUT

# ================================================================
# EXACT CORRECT STATE per key character at May 1st
# Characters not listed will have their relations/secrets stripped
# to self-only known secrets and minimal relations (classmates only)
# ================================================================

# Characters active at May 1st with their correct state
CORRECT_STATE = {
    "绫小路清隆": {
        "secrets": [
            {
                "info_id": "ayanokoji_hidden_ability",
                "content": "绫小路清隆拥有远超常人的身体能力与智力，但他刻意隐藏这一切，只想度过平凡的校园生活。",
                "known_by": ["ayanokoji_kiyotaka"],
            },
            {
                "info_id": "ayanokoji_white_room",
                "content": "绫小路清隆是「白屋」（White Room）的产物，从小接受极端精英教育，是第四期生中唯一的幸存者。他来到这所学校是为了逃离父亲的掌控，获得自由。",
                "known_by": ["ayanokoji_kiyotaka"],
            },
        ],
        "relations": [
            {"to": "堀北铃音", "type": "neutral", "reason": "邻座同学。入学第一天在公车上相遇，之后成为邻座。绫小路觉得堀北和自己一样孤独，偶尔搭话，但远谈不上朋友。"},
            {"to": "栉田桔梗", "type": "neutral", "reason": "同班同学。栉田对所有人都很友善，绫小路表面配合但内心保持警惕——他觉得她过于完美，不自然。"},
            {"to": "须藤健", "type": "neutral", "reason": "同班同学。在便利店帮须藤垫付了泡面钱，须藤因此对他有了印象，但两人还不太熟。"},
            {"to": "池宽治", "type": "neutral", "reason": "同班同学。池创建了男生LINE群组，把绫小路也拉了进去，偶尔闲聊。"},
            {"to": "山内春树", "type": "neutral", "reason": "同班同学。通过池的群组认识，偶尔一起聊天。"},
            {"to": "平田洋介", "type": "neutral", "reason": "同班同学。平田是D班的中心人物，人缘极好。绫小路对他保持距离，避免被卷入班级事务。"},
            {"to": "茶柱佐枝", "type": "neutral", "reason": "D班班导。茶柱佐枝是一个看起来对班级漠不关心的老师，但绫小路隐约感觉到她在观察自己。"},
        ],
    },

    "堀北铃音": {
        "secrets": [
            {
                "info_id": "horikita_brother_complex",
                "content": "堀北铃音对哥哥堀北学有着极深的执念。她来到这所学校、拼命想要升上A班，很大程度上是为了向哥哥证明自己的价值。她冷傲的外表下隐藏着对认可的极度渴望。",
                "known_by": ["horikita_suzune"],
            },
        ],
        "relations": [
            {"to": "绫小路清隆", "type": "neutral", "reason": "邻座同学。入学第一天在公车上相遇，堀北觉得他是个奇怪的家伙——看似不起眼，却偶尔说出有见地的话。她姑且允许他在自己身边待着，但不认为他是朋友。"},
            {"to": "堀北学", "type": "family", "reason": "哥哥，学生会会长。堀北铃音对哥哥有着复杂的情感——既崇拜又自卑，渴望得到他的认可。她不愿让哥哥知道自己在D班。"},
            {"to": "须藤健", "type": "hostile", "reason": "同班同学。须藤是典型的D班废柴——冲动、成绩差、惹是生非。堀北觉得这种人拖累了班级，不想和他有任何瓜葛。"},
            {"to": "栉田桔梗", "type": "hostile", "reason": "同班同学。栉田表面友善，但堀北直觉地不信任她。两人之间有一种微妙的敌意。"},
        ],
    },

    "栉田桔梗": {
        "secrets": [
            {
                "info_id": "kushida_dark_side",
                "content": "栉田桔梗有着极其黑暗的另一面人格。她内心极度厌恶所有人，维持完美形象对她来说是一种折磨。她会利用社交网络收集每个人的秘密和弱点，用于控制和摧毁威胁到她「完美形象」的人。任何可能暴露她真实面目的人都会被她视为必须摧毁的敌人。",
                "known_by": ["kushida_kikyo"],
            },
        ],
        "relations": [
            {"to": "绫小路清隆", "type": "neutral", "reason": "同班同学。栉田注意到绫小路和堀北走得近，对他产生了兴趣——她想通过绫小路了解堀北的弱点。表面保持友善。"},
            {"to": "堀北铃音", "type": "hostile", "reason": "同班同学。堀北是唯一一个对栉田的友善无动于衷的人。栉田视堀北为威胁，想找到她的把柄并摧毁她。"},
            {"to": "平田洋介", "type": "friend", "reason": "同班同学。两人都是班级的核心人物，在班级事务上互相配合。"},
        ],
    },

    "须藤健": {
        "secrets": [],
        "relations": [
            {"to": "绫小路清隆", "type": "friend", "reason": "同班同学。绫小路在便利店帮他垫了钱，须藤觉得这人够意思。虽然交流不多，但须藤把绫小路当朋友。"},
            {"to": "池宽治", "type": "friend", "reason": "同班同学。一起闲聊打混的朋友。"},
            {"to": "山内春树", "type": "friend", "reason": "同班同学。一起闲聊打混的朋友。"},
            {"to": "堀北铃音", "type": "neutral", "reason": "同班同学。觉得堀北很漂亮但太冷了，不怎么敢搭话。"},
        ],
    },

    "平田洋介": {
        "secrets": [
            {
                "info_id": "hirata_trauma",
                "content": "平田洋介在初中时期因为自己的懦弱导致最好的朋友自杀。这份深重的愧疚感驱使他在高中成为一个「完美的好人」——他必须保护所有人，不能拒绝任何人的求助。",
                "known_by": ["hirata_yosuke"],
            },
        ],
        "relations": [
            {"to": "轻井泽惠", "type": "crush", "reason": "同班同学，公开的恋人关系。但这更多是轻井泽寻求保护，平田配合她的需要。"},
            {"to": "绫小路清隆", "type": "neutral", "reason": "同班同学。平田注意到绫小路虽然不起眼但很可靠，有心拉他融入班级。"},
            {"to": "栉田桔梗", "type": "friend", "reason": "同班同学。两人在班级事务上互相协助，是D班的核心人物搭档。"},
        ],
    },

    "轻井泽惠": {
        "secrets": [
            {
                "info_id": "karuizawa_past",
                "content": "轻井泽惠在初中时期曾经是校园霸凌的受害者。那段经历给她留下了深重的心理创伤。她现在的强势外表、和平田的恋爱关系，全都是为了保护自己而建立的「防御系统」。她内心极度恐惧再次被孤立和欺负。",
                "known_by": ["karuizawa_kei"],
            },
        ],
        "relations": [
            {"to": "平田洋介", "type": "crush", "reason": "同班同学，表面上的恋人。对轻井泽来说，平田是她维持自己在班级中地位的「护身符」。"},
        ],
    },

    "池宽治": {
        "secrets": [],
        "relations": [
            {"to": "绫小路清隆", "type": "friend", "reason": "同班同学。池把绫小路拉进了自己的男生群组，觉得他是个好说话的家伙。"},
            {"to": "须藤健", "type": "friend", "reason": "同班同学。经常一起混的朋友。"},
            {"to": "山内春树", "type": "friend", "reason": "同班同学。三人组之一。"},
        ],
    },

    "山内春树": {
        "secrets": [],
        "relations": [
            {"to": "绫小路清隆", "type": "neutral", "reason": "同班同学。偶尔在男生圈子里聊天的对象。"},
            {"to": "池宽治", "type": "friend", "reason": "同班同学，好友。"},
            {"to": "须藤健", "type": "friend", "reason": "同班同学，好友。"},
        ],
    },

    "茶柱佐枝": {
        "secrets": [
            {
                "info_id": "chabashira_past",
                "content": "茶柱佐枝曾经也是高度育成高中的学生，她所在的D班因为她的无能而没能升上A班。这份遗憾驱使她成为了教师，想看看自己这一届的D班能否创造奇迹。",
                "known_by": ["chabashira_sae"],
            },
        ],
        "relations": [
            {"to": "绫小路清隆", "type": "neutral", "reason": "D班学生。茶柱注意到这个学生的入学成绩和实际表现有明显落差，开始暗中关注他。她隐约觉得这个学生不简单。"},
            {"to": "堀北铃音", "type": "neutral", "reason": "D班学生。茶柱看出堀北有潜力，但性格孤傲需要打磨。"},
        ],
    },

    "龙园翔": {
        "secrets": [
            {
                "info_id": "ryuen_ambition",
                "content": "龙园翔以暴力殴打和威胁的手段迫使C班大部分学生臣服，正在建立自己的绝对统治。他享受掌控一切的快感，将全校视为自己的棋盘。",
                "known_by": ["ryuen_kakeru"],
            },
        ],
        "relations": [
            {"to": "石崎大地", "type": "subservient", "reason": "C班学生。被龙园用暴力制服，现在完全服从龙园。"},
            {"to": "伊吹澪", "type": "subservient", "reason": "C班学生。表面服从龙园的统治，但心中不服。"},
        ],
    },

    "石崎大地": {
        "secrets": [],
        "relations": [
            {"to": "龙园翔", "type": "subservient", "reason": "C班实际统治者。石崎对龙园极度畏惧，完全不敢违抗他的命令。"},
        ],
    },

    "伊吹澪": {
        "secrets": [],
        "relations": [
            {"to": "龙园翔", "type": "hostile", "reason": "C班同学。伊吹对龙园的暴力统治心中不服，但暂时没有反抗的力量。"},
        ],
    },

    "一之濑帆波": {
        "secrets": [
            {
                "info_id": "ichinose_past",
                "content": "一之濑帆波在初中时期曾经因为偷窃事件而被迫转学。这件事是她深深的阴影，她发誓要在高中做一个好人来弥补过去的错误。",
                "known_by": ["ichinose_honami"],
            },
        ],
        "relations": [
            {"to": "神崎隆二", "type": "friend", "reason": "同班同学，B班的副手，一之濑最信任的伙伴。"},
        ],
    },

    "堀北学": {
        "secrets": [],
        "relations": [
            {"to": "堀北铃音", "type": "family", "reason": "妹妹。堀北学对妹妹态度冷淡，认为她实力不足，不配做自己的妹妹。但他的严厉底下藏着希望妹妹能独立成长的期望。"},
            {"to": "橘茜", "type": "trust", "reason": "学生会书记，堀北学最信任的助手。"},
        ],
    },

    "高圆寺六助": {
        "secrets": [
            {
                "info_id": "kouenji_confidence",
                "content": "高圆寺六助出身名门，拥有超强的身体能力和自信。他完全不在乎班级点数和个人点数，按照自己的节奏生活。他认为自己是最完美的存在。",
                "known_by": ["kouenji_rokusuke"],
            },
        ],
        "relations": [],
    },

    "外村": {
        "secrets": [],
        "relations": [
            {"to": "绫小路清隆", "type": "friend", "reason": "同班同学。外村（博士）是那种不起眼的宅男型学生，和绫小路一样不爱出风头，两人偶尔在班级角落里闲聊游戏。"},
        ],
    },

    "坂柳有栖": {
        "secrets": [
            {
                "info_id": "sakayanagi_white_room",
                "content": "坂柳有栖知道「白屋」的存在，并且知道绫小路清隆是白屋的最高杰作。她视绫小路为必须击败的对手，但此时尚未与他正式接触。",
                "known_by": ["sakayanagi_arisu"],
            },
        ],
        "relations": [],
    },

    "葛城康平": {
        "secrets": [],
        "relations": [
            {"to": "坂柳有栖", "type": "rival", "reason": "同班同学。葛城与坂柳在A班内部形成了两派对立，争夺班级主导权。"},
        ],
    },

    "神崎隆二": {
        "secrets": [],
        "relations": [
            {"to": "一之濑帆波", "type": "trust", "reason": "同班同学，B班副手。神崎冷静理性，是一之濑最可靠的搭档。"},
        ],
    },

    "橘茜": {
        "secrets": [],
        "relations": [
            {"to": "堀北学", "type": "trust", "reason": "学生会书记，堀北学的忠实助手。"},
        ],
    },

    "佐仓爱里": {
        "secrets": [
            {
                "info_id": "sakura_gravure",
                "content": "佐仓爱里是一名知名网络平面偶像（写真偶像），但她极度害羞内向，不想让任何人知道这个身份。她在班级里几乎不与人交流，是一个存在感极低的学生。",
                "known_by": ["sakura_airi"],
            },
        ],
        "relations": [],
    },

    "椎名日和": {
        "secrets": [],
        "relations": [
            {"to": "龙园翔", "type": "neutral", "reason": "同班同学。椎名是C班少数不受龙园暴力统治影响的人之一，她有自己的原则和底线。"},
        ],
    },

    "松下千秋": {
        "secrets": [],
        "relations": [],
    },

    "幸村辉彦": {
        "secrets": [],
        "relations": [],
    },

    "长谷部": {
        "secrets": [],
        "relations": [],
    },

    "三宅明人": {
        "secrets": [],
        "relations": [],
    },

    "山田阿尔伯特": {
        "secrets": [],
        "relations": [
            {"to": "龙园翔", "type": "subservient", "reason": "C班学生，龙园的忠实手下。"},
        ],
    },

    "星之宫知惠": {
        "secrets": [
            {
                "info_id": "hoshinomiya_chabashira",
                "content": "星之宫知惠是B班班导，与D班班导茶柱佐枝是学生时代的好友。她对茶柱有一种微妙的竞争心结。",
                "known_by": ["hoshinomiya_chie"],
            },
        ],
        "relations": [
            {"to": "茶柱佐枝", "type": "friend", "reason": "学生时代的好友，同为教师。星之宫表面上亲密，但内心有竞争意识。"},
        ],
    },

    "真嶋智也": {
        "secrets": [],
        "relations": [],
    },

    "南云雅": {
        "secrets": [],
        "relations": [
            {"to": "堀北学", "type": "rival", "reason": "二年级A班学生，学生会副会长。南云对堀北学的权威持挑战态度，有取而代之的野心。"},
        ],
        "status_note": "二年级学生，锚点时的存在感低",
    },
}

# Characters that definitely should NOT appear in the data at all
# (duplicates, errors, or too minor)
REMOVE_CHARACTERS = {
    "月城代理理事长", "绫小路笃臣",
    # Duplicates with slightly different names
    "松下千秋 ", "高圆寺", "龙园", "堀北",
}

# Generic classmate names that are probably minor extras or errors
# Keep them but strip all non-self secrets and all relations
STRIP_TO_MINIMAL = {}


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    chars = data["data"]
    corrected = set()
    removed = set()

    for char in chars:
        name = char.get("name", "").strip()

        # Remove error characters
        if name in REMOVE_CHARACTERS:
            removed.add(name)
            continue

        if name in CORRECT_STATE:
            correct = CORRECT_STATE[name]
            char["secrets"] = correct.get("secrets", [])
            char["relations"] = correct.get("relations", [])
            if "status_note" in correct:
                char["status_note"] = correct["status_note"]
            corrected.add(name)
        else:
            # Character not explicitly defined: strip all secrets and relations
            # These are minor characters whose data is unreliable at May 1st
            char["secrets"] = []
            char["relations"] = []

    # Remove characters marked for deletion
    chars = [c for c in chars if c["name"] not in REMOVE_CHARACTERS]

    # Remove duplicates (same name appearing twice)
    seen_names = set()
    unique_chars = []
    for c in chars:
        if c["name"] not in seen_names:
            seen_names.add(c["name"])
            unique_chars.append(c)
    chars = unique_chars

    # Clean traits for all characters
    for char in chars:
        seen = set()
        clean = []
        for t in char.get("traits", []):
            t = t.replace("主义者", "主义").replace("的", "").strip()
            if t and t not in seen and len(t) <= 8:
                seen.add(t)
                clean.append(t)
        char["traits"] = clean[:8]

    # Report
    total_rels = sum(len(c.get("relations", [])) for c in chars)
    total_secs = sum(len(c.get("secrets", [])) for c in chars)

    print(f"Corrected: {len(corrected)} characters with exact state")
    print(f"Removed: {len(removed)} characters")
    print(f"Final count: {len(chars)} characters")
    print(f"Total relations: {total_rels}")
    print(f"Total secrets: {total_secs}")

    # Save
    output = {"type": "characters", "data": chars}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to: {OUTPUT}")


if __name__ == "__main__":
    main()
