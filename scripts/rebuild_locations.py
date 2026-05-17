"""
Rebuild locations_extracted.json based on world_map_desc.txt reference.
- Reference file provides authoritative: location_id, name, zone, connectivity
- Existing extracted JSON provides novel-sourced descriptions where available
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
EXISTING_PATH = os.path.join(OUTPUT_DIR, "locations_extracted.json")


def load_existing_descriptions():
    """Load existing extracted locations for description cross-reference."""
    desc_map = {}
    if os.path.exists(EXISTING_PATH):
        with open(EXISTING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("data", []):
            lid = entry.get("location_id", "")
            desc_map[lid] = {
                "description": entry.get("description", ""),
                "tags": entry.get("tags", []),
            }
    return desc_map


def pick_description(ref_id, ref_desc, existing):
    """Use novel-extracted description if available, otherwise use reference description."""
    # Map similar IDs from existing data to reference IDs
    id_overrides = {
        "classroom_1d": ["classroom_1d", "class_1_d", "classroom_d", "classroom_d_1f"],
        "classroom_1a": ["classroom_1a", "classroom_a"],
        "classroom_1b": ["classroom_1b"],
        "classroom_1c": ["classroom_1c"],
        "classroom_2d": ["classroom_2d"],
        "dorm_student": ["dormitory", "student_dormitory", "dormitory_lobby"],
        "gymnasium": ["gymnasium", "first_gymnasium"],
        "keyaki_mall": ["keyaki_mall", "keyaki_shopping_center"],
        "campus_gate": ["school_gate", "campus_main_gate"],
        "rooftop": ["rooftop"],
        "special_building": ["special_building", "special_teaching_building"],
        "academic_student_council": ["student_council_room", "student_council_office"],
        "admin_office": ["teacher_office", "staff_room"],
        "sports_field": ["school_grounds"],
        "school_bus": ["bus_stop"],
        "event_cruise": ["cruise_ship", "luxury_cruise_ship"],
        "event_island": ["uninhabited_island"],
    }

    # Try mapped IDs from existing data
    for candidate in id_overrides.get(ref_id, [ref_id]):
        if candidate in existing:
            return existing[candidate]["description"]

    return ref_desc


def pick_tags(ref_id, default_tags, existing):
    """Merge reference tags with novel-extracted tags."""
    id_overrides = {
        "classroom_1d": ["classroom_1d", "class_1_d"],
        "dorm_student": ["dormitory", "student_dormitory"],
        "gymnasium": ["gymnasium", "first_gymnasium"],
        "keyaki_mall": ["keyaki_mall", "keyaki_shopping_center"],
        "campus_gate": ["school_gate", "campus_main_gate"],
        "rooftop": ["rooftop"],
        "special_building": ["special_building", "special_teaching_building"],
        "academic_student_council": ["student_council_room", "student_council_office"],
        "admin_office": ["teacher_office", "staff_room"],
        "event_cruise": ["cruise_ship", "luxury_cruise_ship"],
    }

    for candidate in id_overrides.get(ref_id, [ref_id]):
        if candidate in existing:
            return existing[candidate]["tags"]
    return default_tags


def build_locations():
    existing = load_existing_descriptions()

    locations = []

    # ========== 外围与边缘区 ==========
    locations.append({
        "location_id": "campus_gate",
        "name": "正门及周边",
        "description": pick_description("campus_gate",
            "校园的主入口，由天然岩石拼凑加工而成，是学生乘坐公车抵达后进入校园的第一道关口。文化祭时按距离远近设有收费/免费摆摊区。",
            existing),
        "tags": pick_tags("campus_gate", ["outdoor", "public", "landmark"], existing),
        "connected_to": ["school_bus", "academic_hallway", "dorm_student", "sports_field"],
        "zone_id": "campus_perimeter",
    })

    locations.append({
        "location_id": "campus_edge",
        "name": "校区边缘与无人点",
        "description": "包含未经许可禁用的'小型装配屋'以及教学楼背面等非营业区域。人流量极低，适合独处或秘密接触。",
        "tags": ["outdoor", "quiet", "secluded"],
        "connected_to": ["academic_hallway", "special_building"],
        "zone_id": "campus_perimeter",
    })

    # ========== 核心教学与行政区 ==========
    # Academic hallway (corridor hub)
    locations.append({
        "location_id": "academic_hallway",
        "name": "教学楼走廊",
        "description": pick_description("academic_hallway",
            "教学区的枢纽走廊。各楼层走廊（尤其是理科教室附近）装设有无死角的监视器。连接各班级教室、学生会室和职员室。",
            existing),
        "tags": ["indoor", "public", "noisy"],
        "connected_to": [
            "classroom_1a", "classroom_1b", "classroom_1c", "classroom_1d",
            "classroom_2a", "classroom_2b", "classroom_2c", "classroom_2d",
            "classroom_3a", "classroom_3b", "classroom_3c", "classroom_3d",
            "academic_student_council", "admin_office", "guidance_room",
            "campus_gate", "rooftop", "campus_edge",
        ],
        "zone_id": "teaching_building",
    })

    # Classrooms - all 12 (3 years x 4 classes)
    class_names = {
        "1a": "一年A班教室", "1b": "一年B班教室", "1c": "一年C班教室", "1d": "一年D班教室",
        "2a": "二年A班教室", "2b": "二年B班教室", "2c": "二年C班教室", "2d": "二年D班教室",
        "3a": "三年A班教室", "3b": "三年B班教室", "3c": "三年C班教室", "3d": "三年D班教室",
    }
    class_descs = {
        "1d": "一年D班的教室。桌椅有些陈旧，靠窗的后排能看到中庭。教室里弥漫着慵懒散漫的氛围——有人趴着睡觉，有人旁若无人地聊天。天花板角落装有微型监视器。",
        "2d": "位于教学楼二楼，配备有电子黑板和充电设备，桌椅排列整齐。新学期开始，黑板被巨大的萤幕取代，教科书也换成了平板电脑。",
        "1a": "一年A班的教室，气氛严肃，学生自律性极强。坂柳有栖通常坐在前排靠窗位置。",
        "1b": "一年B班的教室，气氛活跃而和谐，一之濑帆波是班级的中心人物。",
        "1c": "一年C班的教室，龙园翔以暴力和恐惧统治着这个班级，气氛压抑。",
    }
    for key in ["1a", "1b", "1c", "1d", "2a", "2b", "2c", "2d", "3a", "3b", "3c", "3d"]:
        lid = f"classroom_{key}"
        desc = class_descs.get(key, f"{class_names[key]}。位于教学楼内，是学生日常上课和班级会议的主要场所。")
        locations.append({
            "location_id": lid,
            "name": class_names[key],
            "description": pick_description(lid, desc, existing),
            "tags": ["indoor", "public"],
            "connected_to": ["academic_hallway"],
            "zone_id": "teaching_building",
        })

    # Student council room
    locations.append({
        "location_id": "academic_student_council",
        "name": "学生会室",
        "description": pick_description("academic_student_council",
            "位于教学楼顶层（四楼）。内设长桌，用于举行正式会议或审议，气氛庄重严肃。是学生会长处理事务、审议学生纠纷的场所。",
            existing),
        "tags": ["indoor", "quiet", "restricted"],
        "connected_to": ["academic_hallway"],
        "zone_id": "teaching_building",
    })

    # Special building
    locations.append({
        "location_id": "special_building",
        "name": "特别教学大楼",
        "description": pick_description("special_building",
            "独立于普通教学楼。平时人烟稀少，不用于社团活动。三楼是校内极少数未设置监视器的盲区（假监视器）。共有三层八间教室，文化祭时可租用。一楼租金最高（5万点），三楼最低（1万-1.3万点）。",
            existing),
        "tags": ["indoor", "quiet", "secluded"],
        "connected_to": ["academic_hallway", "campus_edge"],
        "zone_id": "teaching_building",
    })

    # Admin office
    locations.append({
        "location_id": "admin_office",
        "name": "职员室",
        "description": pick_description("admin_office",
            "教职员办公区，走廊有监视器，严禁学生随意闯入。茶柱老师等教师在此办公，处理学生成绩、点数及纪律事务。",
            existing),
        "tags": ["indoor", "quiet", "restricted"],
        "connected_to": ["academic_hallway"],
        "zone_id": "teaching_building",
    })

    # Guidance room
    locations.append({
        "location_id": "guidance_room",
        "name": "辅导室",
        "description": "专门用于教师与个别学生面谈、面对面辅导的房间。内有独立茶水间，内部没有监控。气氛私密，适合进行深入的个人交流。",
        "tags": ["indoor", "quiet", "private", "restricted"],
        "connected_to": ["academic_hallway"],
        "zone_id": "teaching_building",
    })

    # Rooftop
    locations.append({
        "location_id": "rooftop",
        "name": "屋顶",
        "description": pick_description("rooftop",
            "教学楼顶层，全年开放，装有牢固栅栏。仅门外上方有监视器，内部是极佳的避人耳目之地。可俯瞰整个校园。",
            existing),
        "tags": ["outdoor", "quiet", "secluded", "high"],
        "connected_to": ["academic_hallway"],
        "zone_id": "teaching_building",
    })

    # ========== 运动场地 ==========
    locations.append({
        "location_id": "sports_field",
        "name": "室外操场",
        "description": "教学区外侧，包含跑道与足球场，其他室外体育项目也统一在此进行。校运会在此举办，是学生体育活动和大型户外集会的主要场地。",
        "tags": ["outdoor", "noisy", "large"],
        "connected_to": ["gymnasium", "club_facilities", "campus_gate", "keyaki_mall"],
        "zone_id": "sports_area",
    })

    locations.append({
        "location_id": "gymnasium",
        "name": "体育馆",
        "description": pick_description("gymnasium",
            "室内大型场馆，内部分为多个区域。含上课用游泳池，有专门场馆用于举办大型集会（如开学典礼、社团招新活动）。文化祭时可被包下用于大型摊位。",
            existing),
        "tags": ["indoor", "noisy", "large"],
        "connected_to": ["sports_field", "club_facilities"],
        "zone_id": "sports_area",
    })

    locations.append({
        "location_id": "club_facilities",
        "name": "社团场地",
        "description": "各类社团专用的独立场馆区。包括音乐室、美术室、料理教室、武道场等，放学后社团活动的主要场所。",
        "tags": ["indoor", "noisy"],
        "connected_to": ["sports_field", "gymnasium", "academic_hallway"],
        "zone_id": "sports_area",
    })

    # ========== 生活与商业区 ==========
    locations.append({
        "location_id": "dorm_student",
        "name": "学生宿舍",
        "description": pick_description("dorm_student",
            "共有3栋独立楼宇供学生居住。男女共用大楼但严禁不正当关系。实行严格的房卡管理和倒垃圾/噪音规范。房间为个人专用（约四坪），配有基本家具和空调。同一年级的所有学生住在同一栋楼，男生在低层，女生在高层，主要由电梯上下。",
            existing),
        "tags": ["indoor", "quiet", "restricted", "residential"],
        "connected_to": ["campus_gate", "keyaki_mall", "academic_hallway"],
        "zone_id": "dormitory",
    })

    locations.append({
        "location_id": "dorm_staff",
        "name": "教职员宿舍",
        "description": "供教师及工作人员居住的独立区域，学生一般禁止靠近。环境安静，与教学区和学生宿舍保持一定距离。",
        "tags": ["indoor", "quiet", "restricted"],
        "connected_to": ["campus_edge"],
        "zone_id": "dormitory",
    })

    locations.append({
        "location_id": "keyaki_mall",
        "name": "榉树购物中心",
        "description": pick_description("keyaki_mall",
            "校园内独立的庞大商业区。包含咖啡厅、便利店、电影院、卡拉OK、书店、礼品店、健身房等。是放学后学生最大的聚集地。暑假期间因占卜师活动而热闹非凡。",
            existing),
        "tags": ["indoor", "noisy", "commercial", "public"],
        "connected_to": ["dorm_student", "academic_hallway", "sports_field", "water_paradise"],
        "zone_id": "commercial",
    })

    locations.append({
        "location_id": "water_paradise",
        "name": "水上乐园",
        "description": "包含大量与水有关的娱乐设施：水上排球、跳水台、造浪池、漂流河、各种水滑梯。有独立的更衣室。是暑假玩乐的不二选择。",
        "tags": ["outdoor", "noisy", "recreational", "seasonal"],
        "connected_to": ["keyaki_mall"],
        "zone_id": "commercial",
    })

    # ========== 校外特别地图（仅限特殊事件） ==========
    locations.append({
        "location_id": "school_bus",
        "name": "接驳公交车",
        "description": pick_description("school_bus",
            "将学生从外界都市运送至学校正门的交通工具。仅在新生入学报到或特殊外出时使用。车内座位按班级或随机安排，是新生首次接触同学的地方。",
            existing),
        "tags": ["indoor", "vehicle", "transitional"],
        "connected_to": ["campus_gate"],
        "zone_id": "off_campus_special",
    })

    # Cruise ship
    locations.append({
        "location_id": "event_cruise",
        "name": "豪华游轮·圣维纳斯号",
        "description": pick_description("event_cruise",
            "船名圣维纳斯号。由地上四层、地下四层及屋顶组成。高度育成高中为暑假旅行租用，设施齐全，包括餐厅、游泳池、娱乐设施等。学生在此进行为期两周的巡航旅行，期间进行特别考试。",
            existing),
        "tags": ["indoor", "vehicle", "restricted", "special"],
        "connected_to": [
            "event_cruise_0f", "event_cruise_1f", "event_cruise_2f",
            "event_cruise_3f", "event_cruise_4f",
            "event_cruise_-1f", "event_cruise_-2f", "event_cruise_-3f", "event_cruise_-4f",
        ],
        "zone_id": "off_campus_special",
    })

    cruise_floors = {
        "0f": ("游轮顶层·甲板", "设有露天游泳池和咖啡厅。阳光充足，是学生享受休闲时光的地方。早晨几乎没有学生，适合秘密会面。"),
        "1f": ("游轮一层·宴会厅", "休息室和宴会使用的楼层。空间宽敞，可用于大型聚会和活动。"),
        "2f": ("游轮二层·考试区", "在船上举行特别考试时使用。有多个小型说明间和大型会议室。平日几乎没有学生会去该层。"),
        "3f": ("游轮三层·男生客房", "男生客房区，四人一间。绫小路、平田、高圆寺、幸村同住一间。"),
        "4f": ("游轮四层·女生客房", "女生客房区，四人一间。轻井泽、佐仓等女生居住于此。"),
        "-1f": ("游轮负一层·娱乐区", "设有电影、舞台等娱乐设施，是学生休闲娱乐的场所。"),
        "-2f": ("游轮负二层", "游轮下层区域，包含部分功能设施。"),
        "-3f": ("游轮负三层", "游轮下层区域，机房和储存空间所在。"),
        "-4f": ("游轮负四层·设备层", "游轮最底层，设有配电盘室等机房。与学生生活无关，禁止学生进入。"),
    }
    for floor, (name, desc) in cruise_floors.items():
        locations.append({
            "location_id": f"event_cruise_{floor}",
            "name": name,
            "description": desc,
            "tags": ["indoor", "restricted", "special"],
            "connected_to": ["event_cruise"],
            "zone_id": "off_campus_special",
        })

    # Uninhabited island
    locations.append({
        "location_id": "event_island",
        "name": "无人岛",
        "description": pick_description("event_island",
            "面积约0.5平方公里的荒岛。包含海岸登陆点、内陆河流（核心水源）、森林陡坡以及散布在洞窟或河边的占领'据点'。地形复杂易迷路，天气多变，常有暴雨和浓雾。",
            existing),
        "tags": ["outdoor", "secluded", "dangerous", "special"],
        "connected_to": [
            "event_island_base1", "event_island_base2", "event_island_base3",
            "event_island_beach", "event_island_forest", "event_island_river",
        ],
        "zone_id": "off_campus_special",
    })

    locations.append({
        "location_id": "event_island_beach",
        "name": "无人岛·海滩",
        "description": "无人岛上的沙滩，是考试开始的集合点。学生们在此接受规则说明并选择基地营位置。视野开阔，阳光强烈。",
        "tags": ["outdoor", "noisy", "special"],
        "connected_to": ["event_island", "event_island_forest"],
        "zone_id": "off_campus_special",
    })

    locations.append({
        "location_id": "event_island_forest",
        "name": "无人岛·森林",
        "description": "从海滩通往岛屿内部的森林区域。树木茂密，光线昏暗，地面泥泞，容易迷路。是学生们探索据点的主要通道。",
        "tags": ["outdoor", "quiet", "secluded", "special"],
        "connected_to": ["event_island", "event_island_beach", "event_island_river", "event_island_base1", "event_island_base2", "event_island_base3"],
        "zone_id": "off_campus_special",
    })

    locations.append({
        "location_id": "event_island_river",
        "name": "无人岛·河流",
        "description": "一条宽约十米的清澈河流，是岛上的核心水源。河水可用于饮用和洗澡，但需煮沸。河岸平地常被选为基地营。",
        "tags": ["outdoor", "quiet", "secluded", "special"],
        "connected_to": ["event_island", "event_island_forest", "event_island_base2"],
        "zone_id": "off_campus_special",
    })

    locations.append({
        "location_id": "event_island_base1",
        "name": "无人岛·据点1（洞窟）",
        "description": "位于无人岛边缘地带的一处洞窟洞口处，周围一圈未被树林遮盖。内部经过人工加固，设有占领终端。",
        "tags": ["outdoor", "quiet", "secluded", "special"],
        "connected_to": ["event_island", "event_island_forest"],
        "zone_id": "off_campus_special",
    })

    locations.append({
        "location_id": "event_island_base2",
        "name": "无人岛·据点2（河畔大树）",
        "description": "位于无人岛内陆河流一旁的大树下，是D班选定的基地营之一。靠近水源，易于防守。",
        "tags": ["outdoor", "quiet", "secluded", "special"],
        "connected_to": ["event_island", "event_island_river"],
        "zone_id": "off_campus_special",
    })

    locations.append({
        "location_id": "event_island_base3",
        "name": "无人岛·据点3（瀑布）",
        "description": "位于无人岛内陆瀑布旁，景色壮丽但地形险峻。是岛上最有价值的据点之一。",
        "tags": ["outdoor", "quiet", "secluded", "special"],
        "connected_to": ["event_island", "event_island_forest"],
        "zone_id": "off_campus_special",
    })

    return {"type": "locations", "data": locations}


def main():
    data = build_locations()

    # Backup existing
    if os.path.exists(EXISTING_PATH):
        backup_path = EXISTING_PATH.replace(".json", "_backup_v2.json")
        with open(EXISTING_PATH, "rb") as src:
            with open(backup_path, "wb") as dst:
                dst.write(src.read())
        print(f"Backup: {backup_path}")

    with open(EXISTING_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Written {len(data['data'])} locations to {EXISTING_PATH}")

    # Print zone summary
    zones = {}
    for loc in data["data"]:
        z = loc["zone_id"]
        zones[z] = zones.get(z, 0) + 1
    print("Zone distribution:")
    for z, count in sorted(zones.items()):
        print(f"  {z}: {count}")


if __name__ == "__main__":
    main()
