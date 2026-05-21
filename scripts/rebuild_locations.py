"""
Rebuild locations_extracted.json with hierarchical zone/sub-location structure.

References:
  - world_map_desc.txt: authoritative zone groupings and location IDs
  - Novel data: descriptions sourced from original novels

Output structure:
  - data[]: flat list of all sub-locations with parent_zone, zone_name, floor
  - zones[]: zone definitions with sub_locations lists and entry_points
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "locations_extracted.json")

# ---- Zone definitions ----
ZONES = [
    {
        "zone_id": "teaching_building",
        "name": "教学楼",
        "description": "高度育成高中的核心教学区，四层建筑。一层有主入口、图书馆和教员办公室；二层为一年级教室；三层为二年级教室；四层为三年级教室和学生会室。各层由走廊串联，楼梯和走廊设有监视器。屋顶全年开放，仅门外有监视器，是校内少数监控盲区之一。",
        "type": "campus",
        "sub_locations": [],
        "entry_points": ["hallway_1f"],
    },
    {
        "zone_id": "special_building",
        "name": "特别教学大楼",
        "description": "独立于普通教学楼的建筑。平时人烟稀少，不用于社团活动。三楼是校内极少数未设置监视器的盲区。文化祭时可租用教室摆摊。",
        "type": "campus",
        "sub_locations": [],
        "entry_points": ["special_building_1f"],
    },
    {
        "zone_id": "dormitory",
        "name": "宿舍区",
        "description": "学生居住区，共有3栋独立楼宇。男女共用大楼但严禁不正当关系。实行严格的房卡管理和倒垃圾/噪音规范。同一年级的学生住在同一栋楼，男生在低层，女生在高层。主要由电梯上下楼。",
        "type": "campus",
        "sub_locations": [],
        "entry_points": ["dorm_lobby"],
    },
    {
        "zone_id": "keyaki_mall",
        "name": "榉树购物中心",
        "description": "校园内独立的庞大商业区。包含学生食堂、帕雷特咖啡馆、便利店、电影院、卡拉OK等设施。是放学后学生最大的聚集地，也是学校生活的重要社交场所。",
        "type": "campus",
        "sub_locations": [],
        "entry_points": ["mall_entrance"],
    },
    {
        "zone_id": "event_cruise",
        "name": "豪华游轮·圣维纳斯号",
        "description": "仅在特别考试（如无人岛考试后的船上考试）期间开放。共有地上四层、地下四层及顶层甲板。包含宴会厅、考试区、男女客房、娱乐区等设施。",
        "type": "event",
        "sub_locations": [],
        "entry_points": ["cruise_1f"],
    },
    {
        "zone_id": "event_island",
        "name": "无人岛",
        "description": "仅在特别考试（无人岛生存考试）期间开放。面积约0.5平方公里的荒岛，包含海岸登陆点、内陆河流（核心水源）、森林陡坡，以及散布在洞窟或河边的占领据点。地形复杂易迷路。",
        "type": "event",
        "sub_locations": [],
        "entry_points": ["island_beach"],
    },
]

# ---- All sub-locations ----
LOCATIONS = [
    # === 教学楼 · 走廊 ===
    {"location_id": "hallway_1f", "name": "一层走廊",
     "description": "教学楼一层的主走廊，连接正门方向。公告栏上贴着各类通知和社团招新海报。下课时间学生来来往往，是最繁忙的通道。",
     "tags": ["indoor", "corridor", "public"],
     "connected_to": ["hallway_2f", "library", "teachers_office", "campus_gate", "special_building_1f", "sports_field"],
     "parent_zone": "teaching_building", "floor": "1F"},
    {"location_id": "hallway_2f", "name": "二层走廊",
     "description": "教学楼二层的走廊，一年级教室分布在这一层。课间时一年级学生在此穿梭，偶尔能看到二年级学生经过。",
     "tags": ["indoor", "corridor", "public"],
     "connected_to": ["hallway_1f", "hallway_3f", "classroom_1a", "classroom_1b", "classroom_1c", "classroom_1d"],
     "parent_zone": "teaching_building", "floor": "2F"},
    {"location_id": "hallway_3f", "name": "三层走廊",
     "description": "教学楼三层的走廊，二年级教室分布在这一层。较为安静，偶尔能听到教室里传来的讲课声。",
     "tags": ["indoor", "corridor", "public"],
     "connected_to": ["hallway_2f", "hallway_4f", "classroom_2a", "classroom_2b", "classroom_2c", "classroom_2d"],
     "parent_zone": "teaching_building", "floor": "3F"},
    {"location_id": "hallway_4f", "name": "四层走廊",
     "description": "教学楼四层的走廊，三年级教室和学生会室分布在这一层。临近毕业的三年级学生行色匆匆，气氛比其他楼层更为严肃。",
     "tags": ["indoor", "corridor", "public"],
     "connected_to": ["hallway_3f", "rooftop", "student_council_room", "guidance_room", "classroom_3a", "classroom_3b", "classroom_3c", "classroom_3d"],
     "parent_zone": "teaching_building", "floor": "4F"},

    # === 教学楼 · 一年级教室 ===
    {"location_id": "classroom_1a", "name": "一年A班教室",
     "description": "一年A班的教室。坂柳有栖所在的精英班级，桌椅整齐，氛围严肃认真，学生成绩普遍优异。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
     "parent_zone": "teaching_building", "floor": "2F"},
    {"location_id": "classroom_1b", "name": "一年B班教室",
     "description": "一年B班的教室。一之濑帆波所在的班级，班级凝聚力强，气氛融洽友好。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
     "parent_zone": "teaching_building", "floor": "2F"},
    {"location_id": "classroom_1c", "name": "一年C班教室",
     "description": "一年C班的教室。龙园翔所在的班级，气氛紧张压抑，弥漫着实力至上的残酷竞争氛围。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
     "parent_zone": "teaching_building", "floor": "2F"},
    {"location_id": "classroom_1d", "name": "一年D班教室",
     "description": "一年D班的教室。桌椅有些陈旧，靠窗的后排能看到中庭。教室里弥漫着慵懒散漫的氛围——有人趴着睡觉，有人旁若无人地聊天。这是缺陷品聚集的班级。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
     "parent_zone": "teaching_building", "floor": "2F"},

    # === 教学楼 · 二年级教室 ===
    {"location_id": "classroom_2a", "name": "二年A班教室",
     "description": "二年A班的教室。南云雅所在的班级，气氛紧张且充满竞争性。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
     "parent_zone": "teaching_building", "floor": "3F"},
    {"location_id": "classroom_2b", "name": "二年B班教室",
     "description": "二年B班的教室。桐山生叶所在的班级。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
     "parent_zone": "teaching_building", "floor": "3F"},
    {"location_id": "classroom_2c", "name": "二年C班教室",
     "description": "二年C班的教室。鬼头隼所在的班级。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
     "parent_zone": "teaching_building", "floor": "3F"},
    {"location_id": "classroom_2d", "name": "二年D班教室",
     "description": "二年D班的教室。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
     "parent_zone": "teaching_building", "floor": "3F"},

    # === 教学楼 · 三年级教室 ===
    {"location_id": "classroom_3a", "name": "三年A班教室",
     "description": "三年A班的教室。临近毕业的最高年级精英班级，氛围专注而紧张。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "4F"},
    {"location_id": "classroom_3b", "name": "三年B班教室",
     "description": "三年B班的教室。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "4F"},
    {"location_id": "classroom_3c", "name": "三年C班教室",
     "description": "三年C班的教室。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "4F"},
    {"location_id": "classroom_3d", "name": "三年D班教室",
     "description": "三年D班的教室。",
     "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "4F"},

    # === 教学楼 · 其他房间 ===
    {"location_id": "library", "name": "图书馆",
     "description": "教学楼一层的大型图书馆，藏书丰富，安静整洁。靠窗有一排自习座位，是学生自习和查阅资料的理想场所。",
     "tags": ["indoor", "quiet", "public"], "connected_to": ["hallway_1f"],
     "parent_zone": "teaching_building", "floor": "1F"},
    {"location_id": "student_council_room", "name": "学生会室",
     "description": "位于教学楼四楼的学生会室。内设长桌，用于举行正式会议或审议。气氛庄重严肃，墙上挂着历届学生会成员的照片。",
     "tags": ["indoor", "formal", "restricted"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "4F"},
    {"location_id": "teachers_office", "name": "教员办公室",
     "description": "教职员办公区。走廊有监视器，学生不可随意进入。如需找老师谈话，需在门口说明来意。",
     "tags": ["indoor", "restricted", "quiet"], "connected_to": ["hallway_1f"],
     "parent_zone": "teaching_building", "floor": "1F"},
    {"location_id": "guidance_room", "name": "辅导室",
     "description": "专门用于教师与学生个别面谈的房间。位于四楼，内部有独立茶水间。与普通教室不同，这里没有安装监控设备，是私下交谈的安心场所。",
     "tags": ["indoor", "private", "quiet"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "4F"},
    {"location_id": "rooftop", "name": "屋顶",
     "description": "教学楼顶层，全年开放，装有牢固栅栏。仅门外上方有监视器，内部是绝佳的避人耳目之地，可俯瞰整个校园。风很大，几乎没有人会在这里久留——正因为如此，这里是校内少数可以放心密谈的地点。",
     "tags": ["outdoor", "secluded", "high"], "connected_to": ["hallway_4f"],
     "parent_zone": "teaching_building", "floor": "RF"},

    # === 特别教学大楼 ===
    {"location_id": "special_building_1f", "name": "特别大楼一层",
     "description": "特别教学大楼的一层入口。平时人烟稀少，走廊空旷安静。",
     "tags": ["indoor", "quiet", "public"], "connected_to": ["hallway_1f", "special_building_2f"],
     "parent_zone": "special_building", "floor": "1F"},
    {"location_id": "special_building_2f", "name": "特别大楼二层",
     "description": "特别教学大楼的二层。偶尔用于特别考试或补课，平时几乎无人使用。",
     "tags": ["indoor", "quiet", "restricted"], "connected_to": ["special_building_1f", "special_building_3f"],
     "parent_zone": "special_building", "floor": "2F"},
    {"location_id": "special_building_3f", "name": "特别大楼三层",
     "description": "特别教学大楼的三层。这是校内极少数未安装监视器的盲区。废弃的教室空旷无人，是秘密会面的绝佳场所。",
     "tags": ["indoor", "secluded", "restricted"], "connected_to": ["special_building_2f"],
     "parent_zone": "special_building", "floor": "3F"},

    # === 宿舍区 ===
    {"location_id": "dorm_lobby", "name": "宿舍大厅",
     "description": "学生宿舍的主入口大厅。设有前台、房卡管理系统和电梯间。墙上贴着宿舍管理规范和各类通知。早晚时段学生往来频繁。",
     "tags": ["indoor", "public", "residential"],
     "connected_to": ["dorm_male_floor", "dorm_female_floor", "dorm_courtyard", "campus_gate", "mall_entrance"],
     "parent_zone": "dormitory", "floor": "1F"},
    {"location_id": "dorm_male_floor", "name": "男生楼层",
     "description": "男生宿舍楼层。走廊两侧排列着各自的单人房间（约四坪），配备基本家具和空调。同年级的男生集中居住在此。",
     "tags": ["indoor", "private", "residential"], "connected_to": ["dorm_lobby"],
     "parent_zone": "dormitory"},
    {"location_id": "dorm_female_floor", "name": "女生楼层",
     "description": "女生宿舍楼层，位于男生楼层之上。走廊整洁安静，每间房为个人专用。严禁男生进入。",
     "tags": ["indoor", "private", "restricted"], "connected_to": ["dorm_lobby"],
     "parent_zone": "dormitory"},
    {"location_id": "dorm_courtyard", "name": "宿舍中庭",
     "description": "宿舍楼之间的户外空间。有几张长椅和绿化带，偶尔有学生在傍晚时分在此闲聊或等人。",
     "tags": ["outdoor", "quiet", "residential"], "connected_to": ["dorm_lobby"],
     "parent_zone": "dormitory", "floor": "GF"},

    # === 榉树购物中心 ===
    {"location_id": "mall_entrance", "name": "购物中心入口",
     "description": "榉树购物中心的主入口。玻璃大门上贴着促销海报和营业时间。放学后这里是最热闹的地方。",
     "tags": ["indoor", "public", "commercial"],
     "connected_to": ["mall_cafeteria", "mall_cafe", "mall_shop", "mall_entertainment", "dorm_lobby"],
     "parent_zone": "keyaki_mall", "floor": "1F"},
    {"location_id": "mall_cafeteria", "name": "学生食堂",
     "description": "榉树购物中心内最大的学生食堂。提供价格不等的套餐——免费简餐到丰盛定食都有。午间高峰期座无虚席，是学生社交和信息交换的核心场所。",
     "tags": ["indoor", "noisy", "commercial", "public"], "connected_to": ["mall_entrance"],
     "parent_zone": "keyaki_mall", "floor": "1F"},
    {"location_id": "mall_cafe", "name": "帕雷特咖啡馆",
     "description": "购物中心内的时尚咖啡馆。提供咖啡、茶饮和精致甜点，价格略高于食堂。环境安静舒适，是女生团体和情侣偏爱的场所。",
     "tags": ["indoor", "quiet", "commercial", "public"], "connected_to": ["mall_entrance"],
     "parent_zone": "keyaki_mall", "floor": "1F"},
    {"location_id": "mall_shop", "name": "便利店",
     "description": "购物中心内的便利店，货架上摆满了零食、饮料、文具和日常用品。价格比校外稍贵，但在封闭校园中这就是唯一的购物选择。",
     "tags": ["indoor", "commercial", "public"], "connected_to": ["mall_entrance"],
     "parent_zone": "keyaki_mall", "floor": "1F"},
    {"location_id": "mall_entertainment", "name": "娱乐区",
     "description": "购物中心的娱乐区域，包含电影院和卡拉OK包厢。周末和假日这里需要提前预约，是学生的解压圣地。",
     "tags": ["indoor", "noisy", "commercial", "public"], "connected_to": ["mall_entrance"],
     "parent_zone": "keyaki_mall", "floor": "1F"},

    # === 豪华游轮 ===
    {"location_id": "cruise_0f", "name": "游轮顶层·露天甲板",
     "description": "圣维纳斯号的顶层露天甲板。设有游泳池和咖啡厅，可眺望无垠的大海。海风拂面，视野开阔，是游轮上最令人放松的场所。",
     "tags": ["outdoor", "leisure", "scenic"], "connected_to": ["cruise_1f"],
     "parent_zone": "event_cruise", "floor": "RF"},
    {"location_id": "cruise_1f", "name": "游轮一层·宴会厅",
     "description": "游轮一层的主宴会厅。华丽的吊灯、铺着白桌布的长桌，用于举办宴会和大型集会。",
     "tags": ["indoor", "formal", "large"], "connected_to": ["cruise_0f", "cruise_2f", "cruise_b1f"],
     "parent_zone": "event_cruise", "floor": "1F"},
    {"location_id": "cruise_2f", "name": "游轮二层·考试区",
     "description": "在船上举行特别考试时使用的楼层。设有多个小型说明间和大型会议室。平日几乎没有学生会来这一层。",
     "tags": ["indoor", "formal", "restricted"], "connected_to": ["cruise_1f", "cruise_3f"],
     "parent_zone": "event_cruise", "floor": "2F"},
    {"location_id": "cruise_3f", "name": "游轮三层·男生客房",
     "description": "男生客房楼层。四人一间房，配有基本住宿设施。走廊铺着深色地毯。",
     "tags": ["indoor", "private", "residential"], "connected_to": ["cruise_2f", "cruise_4f"],
     "parent_zone": "event_cruise", "floor": "3F"},
    {"location_id": "cruise_4f", "name": "游轮四层·女生客房",
     "description": "女生客房楼层。四人一间房，装修比男生楼层更精致。严禁男生进入。",
     "tags": ["indoor", "private", "restricted"], "connected_to": ["cruise_3f"],
     "parent_zone": "event_cruise", "floor": "4F"},
    {"location_id": "cruise_b1f", "name": "游轮负一层·娱乐区",
     "description": "游轮地下一层的娱乐区域，设有各种休闲设施供乘客打发时间。",
     "tags": ["indoor", "leisure", "public"], "connected_to": ["cruise_1f", "cruise_b2f"],
     "parent_zone": "event_cruise", "floor": "B1"},
    {"location_id": "cruise_b2f", "name": "游轮负二层",
     "description": "游轮地下二层。",
     "tags": ["indoor", "restricted"], "connected_to": ["cruise_b1f", "cruise_b3f"],
     "parent_zone": "event_cruise", "floor": "B2"},
    {"location_id": "cruise_b3f", "name": "游轮负三层",
     "description": "游轮地下三层。",
     "tags": ["indoor", "restricted"], "connected_to": ["cruise_b2f", "cruise_b4f"],
     "parent_zone": "event_cruise", "floor": "B3"},
    {"location_id": "cruise_b4f", "name": "游轮负四层·设备层",
     "description": "游轮最底层，主要为机械设备区域。一般乘客不会来此。",
     "tags": ["indoor", "restricted", "mechanical"], "connected_to": ["cruise_b3f"],
     "parent_zone": "event_cruise", "floor": "B4"},

    # === 无人岛 ===
    {"location_id": "island_beach", "name": "无人岛·海滩",
     "description": "无人岛的海滩登陆点。白沙与碧海相接，是考试开始时学生们被投放的地点。沙滩上有零星的漂流木和贝壳。",
     "tags": ["outdoor", "coastal", "wild"], "connected_to": ["island_forest"],
     "parent_zone": "event_island"},
    {"location_id": "island_forest", "name": "无人岛·森林",
     "description": "覆盖岛屿大部分面积的密林。树木茂密，光线斑驳。地面不平，时有树根绊脚。林中有多条小路通向各处据点。",
     "tags": ["outdoor", "forest", "wild"],
     "connected_to": ["island_beach", "island_river", "island_base1", "island_base2", "island_base3"],
     "parent_zone": "event_island"},
    {"location_id": "island_river", "name": "无人岛·河流",
     "description": "穿过岛屿内陆的清澈河流，是无人岛上唯一的核心水源。水质清甜可直接饮用。河畔较为开阔，适合休息和补给。",
     "tags": ["outdoor", "water", "wild"], "connected_to": ["island_forest", "island_base2"],
     "parent_zone": "event_island"},
    {"location_id": "island_base1", "name": "无人岛·据点1（洞窟）",
     "description": "位于岛屿边缘一处洞窟洞口的据点。洞口周围未被树林遮盖，视野较好，易守难攻。洞内阴凉干燥，可避风雨。",
     "tags": ["outdoor", "cave", "strategic"], "connected_to": ["island_forest"],
     "parent_zone": "event_island"},
    {"location_id": "island_base2", "name": "无人岛·据点2（河畔大树）",
     "description": "位于内陆河流旁一棵巨树下的据点。临近水源，地势平坦，是最适合扎营的地点之一。",
     "tags": ["outdoor", "riverside", "strategic"], "connected_to": ["island_forest", "island_river"],
     "parent_zone": "event_island"},
    {"location_id": "island_base3", "name": "无人岛·据点3（瀑布）",
     "description": "位于岛屿内陆瀑布旁的据点。瀑布的轰鸣声掩盖了说话声，是密谈的好地方。",
     "tags": ["outdoor", "waterfall", "strategic"], "connected_to": ["island_forest"],
     "parent_zone": "event_island"},

    # === 独立地点 ===
    {"location_id": "campus_gate", "name": "正门及周边",
     "description": "校园的主入口，由天然岩石拼凑加工而成。早晨和放学时学生往来频繁，是校园与外界的分界点。文化祭时按距离远近设有收费/免费摆摊区。",
     "tags": ["outdoor", "public", "landmark"],
     "connected_to": ["school_bus", "hallway_1f", "dorm_lobby", "sports_field"],
     "parent_zone": None, "zone_name": "校园外围"},
    {"location_id": "school_bus", "name": "接驳公交车",
     "description": "将学生从外界都市运送至学校正门的交通工具。仅在新生入学报到或特殊外出时使用。车内座位舒适，窗外校园景色逐渐映入眼帘。",
     "tags": ["indoor", "vehicle", "transitional"], "connected_to": ["campus_gate"],
     "parent_zone": None, "zone_name": "校外"},
    {"location_id": "sports_field", "name": "室外操场",
     "description": "标准的田径运动场，包含跑道与足球场。足球部和田径部在这里训练，校运会在此举办。周围有看台和少量健身器材。",
     "tags": ["outdoor", "sports", "large"],
     "connected_to": ["gymnasium", "campus_gate", "hallway_1f"],
     "parent_zone": None, "zone_name": "运动区"},
    {"location_id": "gymnasium", "name": "体育馆",
     "description": "宽敞的室内体育馆，配备了可移动舞台。细分有多个场馆，内含上课用游泳池。可容纳全校学生，用于举行开学典礼、社团招新等大型集会。",
     "tags": ["indoor", "large", "noisy"],
     "connected_to": ["sports_field", "hallway_1f"],
     "parent_zone": None, "zone_name": "运动区"},
]


def main():
    # Build zone sub_locations lists
    zone_lookup = {z["zone_id"]: z for z in ZONES}
    for loc in LOCATIONS:
        zid = loc.get("parent_zone")
        if zid and zid in zone_lookup:
            zone_lookup[zid]["sub_locations"].append(loc["location_id"])
        # Set zone_name from parent_zone
        if zid and zid in zone_lookup and "zone_name" not in loc:
            loc["zone_name"] = zone_lookup[zid]["name"]

    output = {"data": LOCATIONS, "zones": ZONES}

    # Backup existing
    if os.path.exists(OUTPUT_PATH):
        backup_path = OUTPUT_PATH.replace(".json", "_backup_v3.json")
        import shutil
        shutil.copy2(OUTPUT_PATH, backup_path)
        print(f"Backup: {backup_path}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Written {len(LOCATIONS)} locations and {len(ZONES)} zones to {OUTPUT_PATH}")
    for z in ZONES:
        print(f"  [{z['zone_id']}] {z['name']}: {len(z['sub_locations'])} sub-locations")


if __name__ == "__main__":
    main()
