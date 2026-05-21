"""
Add gender field to all 87 characters in characters_extracted.json.

Gender assignments based on:
- Classroom of the Elite source material (light novels, anime)
- Web research for uncertain names
- Japanese naming conventions where explicit info unavailable
"""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scripts/output/characters_extracted.json', 'r', encoding='utf-8') as f:
    chars = json.load(f)

# Complete gender map for all 87 characters
GENDER_MAP: dict[str, str] = {
    # ═══════════════════════════════════════════════════════
    # D班 1年级 (2024) - 已在原 GENDER_MAP 中
    # ═══════════════════════════════════════════════════════
    "绫小路清隆": "male",
    "堀北铃音": "female",
    "栉田桔梗": "female",
    "须藤健": "male",
    "池宽治": "male",
    "山内春树": "male",
    "平田洋介": "male",
    "高圆寺六助": "male",
    "轻井泽惠": "female",
    "佐仓爱里": "female",
    "井之头心": "female",
    "本堂": "male",
    "小野寺": "female",
    "外村": "male",
    "筱原皋月": "female",
    "幸村辉彦": "male",
    "外村秀雄": "male",
    "佐藤麻耶": "female",
    "长谷部波琉加": "female",
    "松下": "female",
    "三宅明人": "male",
    "姬野": "female",
    "松下千秋": "female",

    # ═══════════════════════════════════════════════════════
    # B班 1年级 (2024) - 已在原 GENDER_MAP 中
    # ═══════════════════════════════════════════════════════
    "一之濑帆波": "female",
    "长谷部波瑠加": "female",
    "神崎隆二": "male",
    "滨口哲也": "male",
    "柴田飒": "male",
    "姬野雪": "female",

    # ═══════════════════════════════════════════════════════
    # C班 1年级 (2024) - 已在原 GENDER_MAP 中
    # ═══════════════════════════════════════════════════════
    "龙园翔": "male",
    "石崎大地": "male",
    "山胁": "male",
    "伊吹澪": "female",
    "真锅志保": "female",
    "石崎": "male",
    "阿尔伯特": "male",
    "真锅": "female",
    "椎名日和": "female",
    "白波千寻": "female",
    "小桥梦": "female",
    "西野武子": "female",

    # ═══════════════════════════════════════════════════════
    # A班 1年级 (2024) - 已在原 GENDER_MAP 中
    # ═══════════════════════════════════════════════════════
    "葛城康平": "male",
    "弥彦": "male",
    "町田浩二": "male",
    "坂柳有栖": "female",
    "神室真澄": "female",
    "桥本正义": "male",
    "竹本": "male",
    "鬼头隼": "male",
    "真田康生": "male",
    "山村美纪": "female",

    # ═══════════════════════════════════════════════════════
    # 1年级 (2025) - White Room 相关 / 新生
    # ═══════════════════════════════════════════════════════
    "七濑翼": "female",       # 白房子第5期生，伪装男性但实为女性
    "八神拓也": "male",       # 白房子第5期生
    "天泽一夏": "female",     # 白房子第5期生
    "宝泉和彦": "male",       # 1年级D班问题学生
    "宝泉和臣": "male",       # 1年级生 (可能与和彦为同一人不同译名)
    "椿樱子": "female",       # 1年级C班，擅操纵人心
    "石上优": "male",         # 1年级A班 (石上家系)

    # ═══════════════════════════════════════════════════════
    # 2-3年级 (2022-2023)
    # ═══════════════════════════════════════════════════════
    "堀北学": "male",         # 学生会长，堀北铃音之兄
    "南云雅": "male",         # 前学生会长，2年级A班
    "橘茜": "female",         # 学生会书记，暗恋堀北学
    "朝比奈荠": "female",     # 3年级A班，南云雅的好友
    "桐山": "male",           # 学生会副会长
    "桐山生": "male",         # 与桐山为同一人
    "桐山龙二": "male",       # 可能是桐山的全名或亲属
    "鬼龙院枫花": "female",   # 2年级A班 (原B班)，实力派
    "三木谷": "male",         # B班学生，一之濑的同伴

    # ═══════════════════════════════════════════════════════
    # 教师 / 职员
    # ═══════════════════════════════════════════════════════
    "茶柱佐枝": "female",     # D班班主任
    "星之宫知惠": "female",    # B班班主任
    "真嶋老师": "male",       # A班班主任 (真嶋智也)
    "司马老师": "male",       # 司马 (Shiba)，体育教师/白房子相关人员
    "鬼岛老师": "male",       # 鬼岛相关 (本校政治辖区名，或首相鬼岛)
    "直江老师": "male",       # 直江仁之助，政治家，白房子计划发案者

    # ═══════════════════════════════════════════════════════
    # 校外 / 白房子 / 其他
    # ═══════════════════════════════════════════════════════
    "坂柳成守": "male",       # 坂柳有栖之父，前理事长
    "月城": "male",           # 月城常成，代理理事长
    "天泽社长": "male",       # 天泽一夏的亲属，可能为公司社长
    "雪": "female",           # 白房子第4期生，清隆的同代
    "雪的父亲": "male",       # 雪的父亲
    "美香": "female",         # 王美雨 (Mii-chan)，D班中国留学生

    # ═══════════════════════════════════════════════════════
    # 白房子研究员 / 工作人员 (D班 N/A)
    # ═══════════════════════════════════════════════════════
    "宗谷": "male",           # 白房子研究员
    "石田": "male",           # 白房子研究员 / 绫小路家执事
    "田渊": "male",           # 白房子研究员
    "石上五郎": "male",       # 石上家系 (石上京之父推测)
    "石上京": "male",         # 石上家系
    "铃悬锻冶": "male",       # 1年级新生，东大首席级学霸
    "神崎智弘": "male",       # 可能与神崎隆二为亲属的白房子人员
    "鸭川": "male",           # 鸭川俊三之子，白房子共同设立者
}

# Apply genders
updated = 0
missing = []
for entry in chars['data']:
    name = entry.get('name', '')
    if not name:
        continue
    if name in GENDER_MAP:
        entry['gender'] = GENDER_MAP[name]
        updated += 1
    else:
        missing.append(name)

# Write back
with open('scripts/output/characters_extracted.json', 'w', encoding='utf-8') as f:
    json.dump(chars, f, ensure_ascii=False, indent=2)

print(f"Updated {updated} characters with gender field")
if missing:
    print(f"\nWARNING: {len(missing)} characters still missing gender:")
    for m in missing:
        print(f"  - {m}")
else:
    print("All characters have gender assigned!")

# Stats
male_count = sum(1 for c in chars['data'] if c.get('gender') == 'male')
female_count = sum(1 for c in chars['data'] if c.get('gender') == 'female')
print(f"\nGender distribution: male={male_count}, female={female_count}")
