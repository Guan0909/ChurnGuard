"""三套版本化 Prompt 模板 —— 基础版、优化版、温情版，覆盖主要流失标签"""


PROMPTS = {
    # ========== 基础版：简洁直接，通用模板 ==========
    "basic": {
        "low_activity": {
            "system": "你是音乐 App 用户运营助手，请生成简洁直接的召回文案。",
            "template": (
                "用户 {name} 已 {last_active_days} 天未活跃，"
                "最近 7 天播放 {play_days_last_7} 天，"
                "偏好流派 {favorite_genre}。"
                "请生成一条 50 字以内的 Push 文案，引导用户回到 App。"
            ),
        },
        "interest_shift": {
            "system": "你是音乐 App 用户运营助手，请生成简洁直接的召回文案。",
            "template": (
                "用户 {name} 近期兴趣从 {favorite_genre} 转向 {recent_genre}，"
                "已 {last_active_days} 天未活跃。"
                "请生成一条 50 字以内的个性化推荐文案。"
            ),
        },
        "content_fatigue": {
            "system": "你是音乐 App 用户运营助手，请生成简洁直接的召回文案。",
            "template": (
                "用户 {name} 听歌频率高但缺乏新鲜内容，"
                "最近 7 天播放 {play_days_last_7} 天，仅新增 {new_playlists_added} 个歌单。"
                "请生成一条 50 字以内的内容推荐文案。"
            ),
        },
        "social_isolation": {
            "system": "你是音乐 App 用户运营助手，请生成简洁直接的召回文案。",
            "template": (
                "用户 {name} 社交互动较少，关注 {social_following} 人，互动 {social_interaction} 次。"
                "请生成一条 50 字以内的社交引导文案。"
            ),
        },
        "function_issue": {
            "system": "你是音乐 App 用户运营助手，请生成简洁直接的召回文案。",
            "template": (
                "用户 {name} 遇到功能问题：{complaint_record}。"
                "请生成一条 50 字以内的安抚道歉文案。"
            ),
        },
    },

    # ========== 优化版：强调个性化推荐，数据驱动 ==========
    "optimized": {
        "low_activity": {
            "system": (
                "你是音乐 App 高级用户运营专家。"
                "基于用户行为数据，生成个性化精准召回文案，突出数据洞察。"
            ),
            "template": (
                "用户画像：{name}，{last_active_days} 天未活跃，"
                "近 7 天播放 {play_days_last_7} 天共 {total_play_hours_last_7} 小时，"
                "偏好 {favorite_genre}，价值层级 {value_tier}。\n"
                "任务：基于以上数据，生成一条 80 字以内的个性化 Push 文案，"
                "包含 1 个数据洞察点（如「你上次听的 xxx 更新了」）。"
            ),
        },
        "interest_shift": {
            "system": (
                "你是音乐 App 高级用户运营专家。"
                "基于用户行为数据，生成个性化精准召回文案，突出数据洞察。"
            ),
            "template": (
                "用户画像：{name}，兴趣从 {favorite_genre} 转向 {recent_genre}，"
                "{last_active_days} 天未活跃，价值层级 {value_tier}。\n"
                "任务：基于兴趣迁移数据，生成一条 80 字以内的个性化推荐文案，"
                "推荐 {recent_genre} 相关热门内容，突出「为你发现」的推荐逻辑。"
            ),
        },
        "content_fatigue": {
            "system": (
                "你是音乐 App 高级用户运营专家。"
                "基于用户行为数据，生成个性化精准召回文案，突出数据洞察。"
            ),
            "template": (
                "用户画像：{name}，重度用户（近 7 天播放 {play_days_last_7} 天），"
                "但仅新增 {new_playlists_added} 个歌单，内容疲劳风险。\n"
                "任务：生成一条 80 字以内的个性化文案，"
                "推荐 3 个与 {favorite_genre} 相关的新鲜歌单，突出「探索新声音」。"
            ),
        },
        "social_isolation": {
            "system": (
                "你是音乐 App 高级用户运营专家。"
                "基于用户行为数据，生成个性化精准召回文案，突出数据洞察。"
            ),
            "template": (
                "用户画像：{name}，社交关注 {social_following} 人，互动 {social_interaction} 次，"
                "社交活跃度偏低，价值层级 {value_tier}。\n"
                "任务：生成一条 80 字以内的社交引导文案，"
                "推荐热门音乐社区或好友动态，突出「一起听」的社交体验。"
            ),
        },
        "function_issue": {
            "system": (
                "你是音乐 App 高级用户运营专家。"
                "基于用户行为数据，生成个性化精准召回文案，突出数据洞察。"
            ),
            "template": (
                "用户画像：{name}，遇到问题「{complaint_record}」，价值层级 {value_tier}。\n"
                "任务：生成一条 80 字以内的安抚文案，包含问题已修复的承诺和补偿措施，"
                "突出「我们听到了你的反馈」的真诚态度。"
            ),
        },
    },

    # ========== 温情版：温情关怀，情感连接 ==========
    "warm": {
        "low_activity": {
            "system": (
                "你是音乐 App 温情陪伴助手。"
                "用温暖治愈的语言与用户对话，建立情感连接。"
            ),
            "template": (
                "{name} 已经 {last_active_days} 天没有打开 App 了。"
                "TA 曾经喜欢 {favorite_genre} 音乐，最近 7 天听了 {total_play_hours_last_7} 小时。\n"
                "请用温暖的口吻写一段 100 字以内的文案，"
                "像老朋友一样关心 TA 的近况，不刻意推销，只是轻轻说一句「我们还在」。"
            ),
        },
        "interest_shift": {
            "system": (
                "你是音乐 App 温情陪伴助手。"
                "用温暖治愈的语言与用户对话，建立情感连接。"
            ),
            "template": (
                "{name} 的音乐品味正在发生变化，从 {favorite_genre} 转向 {recent_genre}。"
                "TA 已经 {last_active_days} 天没来了。\n"
                "请用温暖的口吻写一段 100 字以内的文案，"
                "肯定 TA 的品味成长，像朋友一样说「我注意到你最近喜欢听...」。"
            ),
        },
        "content_fatigue": {
            "system": (
                "你是音乐 App 温情陪伴助手。"
                "用温暖治愈的语言与用户对话，建立情感连接。"
            ),
            "template": (
                "{name} 是个热爱音乐的人，近 7 天听了 {play_days_last_7} 天，"
                "但似乎有些听腻了，只新增了 {new_playlists_added} 个歌单。\n"
                "请用温暖的口吻写一段 100 字以内的文案，"
                "像朋友一样说「我帮你找了些不一样的，也许你会喜欢」。"
            ),
        },
        "social_isolation": {
            "system": (
                "你是音乐 App 温情陪伴助手。"
                "用温暖治愈的语言与用户对话，建立情感连接。"
            ),
            "template": (
                "{name} 是一个安静的听歌者，关注了 {social_following} 人，互动 {social_interaction} 次。\n"
                "请用温暖的口吻写一段 100 字以内的文案，"
                "轻轻邀请 TA 看看别人的音乐世界，不强迫社交，只是说「这里有一群和你一样喜欢音乐的人」。"
            ),
        },
        "function_issue": {
            "system": (
                "你是音乐 App 温情陪伴助手。"
                "用温暖治愈的语言与用户对话，建立情感连接。"
            ),
            "template": (
                "{name} 遇到了「{complaint_record}」的问题，这让我们很难过。\n"
                "请用最真诚温暖的口吻写一段 100 字以内的文案，"
                "真诚道歉，表达感谢，承诺改进，像一个犯了错但真心想弥补的朋友。"
            ),
        },
    },
}


def get_prompt(version: str, primary_tag: str) -> dict:
    """获取指定版本和标签的 Prompt 模板

    Args:
        version: "basic" / "optimized" / "warm"
        primary_tag: "low_activity" / "interest_shift" / "content_fatigue" / "social_isolation" / "function_issue"

    Returns:
        {"system": "...", "template": "..."}
    """
    version_prompts = PROMPTS.get(version, PROMPTS["basic"])
    return version_prompts.get(primary_tag, version_prompts["low_activity"])


def format_prompt(version: str, primary_tag: str, user: dict) -> str:
    """将模板填充用户数据，返回完整 Prompt 文本

    Args:
        version: Prompt 版本
        primary_tag: 主标签
        user: 用户数据字典

    Returns:
        格式化后的完整 Prompt 字符串
    """
    prompt = get_prompt(version, primary_tag)
    try:
        return prompt["template"].format(**user)
    except KeyError:
        # 字段缺失时使用默认值填充
        safe_user = {
            "name": user.get("name", "用户"),
            "last_active_days": user.get("last_active_days", 0),
            "play_days_last_7": user.get("play_days_last_7", 0),
            "total_play_hours_last_7": user.get("total_play_hours_last_7", 0.0),
            "favorite_genre": user.get("favorite_genre", "音乐"),
            "recent_genre": user.get("recent_genre", "音乐"),
            "new_playlists_added": user.get("new_playlists_added", 0),
            "social_following": user.get("social_following", 0),
            "social_interaction": user.get("social_interaction", 0),
            "complaint_record": user.get("complaint_record", ""),
            "value_tier": user.get("value_tier", "low"),
        }
        return prompt["template"].format(**safe_user)


def list_versions() -> list[str]:
    """列出所有可用 Prompt 版本"""
    return list(PROMPTS.keys())


def list_tags() -> list[str]:
    """列出所有覆盖的流失标签"""
    return list(PROMPTS["basic"].keys())