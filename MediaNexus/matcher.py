# -*- coding: utf-8 -*-
"""
MediaNexus - 智能匹配引擎（核心）
匹配策略优先级：完全匹配(100) > 包含匹配(>=88) > 编辑距离匹配(rapidfuzz 评分)
特殊处理：匹配前对名称做归一化，剥离常见后缀 / 版本号 / 冗余符号 / 剧集前缀。
"""
from __future__ import annotations

import re
from functools import lru_cache

from rapidfuzz import fuzz

from .constants import DEFAULT_STRIP_SUFFIXES

# 归一化用的正则
_RE_PAREN_VER = re.compile(r"\(\s*\d+\s*\)")          # (1) ( 2 )
_RE_VER = re.compile(r"[-_ ]?v\d+", re.IGNORECASE)     # _v2  -V1
_RE_TRAILING_YEAR = re.compile(r"[_ -]?20\d{2}$")     # _2024
_RE_LEADING_EP = re.compile(r"^\d+[\.\-_]\d+\s+")     # 6.29  6-29  6_29  等集数/日期前缀
_RE_SPACES = re.compile(r"\s+")
_RE_BRACKET = re.compile(r"[【\[\(（].*?[】\]\)）]")    # 中文/英文括号内容

# token 级清洗：判定「纯噪声」词（日期、集数、状态标记），用于去首尾
_RE_EP_RANGE = re.compile(r"^第?\d+[-~至到]\d+\s*集?$")   # 1-60集 / 第1-60集 / 1~60
_RE_EP_COUNT = re.compile(r"^\d+\s*集$")                  # 60集
_RE_NUMERIC = re.compile(r"^\d+$")                        # 纯数字（日期碎片/年份）
# 短剧本地常见的状态/交付后缀词（作为独立 token 时剥离）
_NOISE_WORDS = {"交", "待交", "已交", "未交", "初剪", "精剪", "成片", "样片", "送审", "网大"}


def _is_leading_noise(tok: str) -> bool:
    return bool(_RE_NUMERIC.match(tok))


def _is_trailing_noise(tok: str) -> bool:
    return (
        bool(_RE_NUMERIC.match(tok))
        or bool(_RE_EP_RANGE.match(tok))
        or bool(_RE_EP_COUNT.match(tok))
        or tok in _NOISE_WORDS
    )

# 中文/英文标点统一替换为空格，便于 token 匹配
_PUNCT_MAP = {
    "，": " ", "。": " ", "、": " ", "：": " ", "；": " ", "！": " ", "？": " ",
    "\"": " ", "“": " ", "”": " ", "‘": " ", "’": " ", "《": " ", "》": " ",
    "（": " ", "）": " ", "【": " ", "】": " ", "［": " ", "］": " ",
}
_PUNCT_TRANS = str.maketrans(_PUNCT_MAP)


@lru_cache(maxsize=4096)
def normalize_name(name: str) -> str:
    """
    名称归一化：在不破坏语义的前提下，去除干扰后缀与符号，统一为小写可比串。
    例：「6.29 龙王归来_2024_剪辑版」 -> 「龙王归来」
    """
    if not name:
        return ""
    s = name.strip()
    # 1) 去除内外层括号内容（如「(1)」「【样片】」）
    s = _RE_BRACKET.sub("", s)
    s = _RE_PAREN_VER.sub("", s)
    # 2) 去除尾随年份
    s = _RE_TRAILING_YEAR.sub("", s)
    # 3) 去除版本号
    s = _RE_VER.sub("", s)
    # 4) 去除开头集数/日期前缀（短剧常见：6.29 / 6-29 / 6_29）
    s = _RE_LEADING_EP.sub("", s)
    # 5) 去除预定义的常见后缀
    changed = True
    while changed:
        changed = False
        for suf in DEFAULT_STRIP_SUFFIXES:
            if s.endswith(suf):
                s = s[: -len(suf)]
                changed = True
    # 6) 标点统一替换为空格，避免「你永不知，我曾有多爱你」和「你永不知 我曾有多爱你」不一致
    s = s.translate(_PUNCT_TRANS)
    s = s.replace(",", " ").replace(".", " ").replace(":", " ")
    # 7) 去首尾分隔符与空白，折叠内部空格
    s = s.strip().strip("_").strip("-").strip()
    s = _RE_SPACES.sub(" ", s)
    # 8) token 级清洗：剥离开头的日期/年份碎片、结尾的集数/状态标记
    tokens = s.split()
    while tokens and _is_leading_noise(tokens[0]):
        tokens.pop(0)
    while tokens and _is_trailing_noise(tokens[-1]):
        tokens.pop()
    # 兜底：若清洗后为空（整名都是数字），退回未清洗版本，避免匹配崩塌
    if tokens:
        s = " ".join(tokens)
    return s.lower()


def score_pair(local_name: str, nas_name: str) -> tuple[int, str]:
    """
    对一对名称打分。
    返回 (score 0-100, strategy)
    strategy ∈ {"exact", "contains", "edit_distance"}
    """
    na, nb = normalize_name(local_name), normalize_name(nas_name)
    if not na or not nb:
        return (0, "edit_distance")
    if na == nb:
        return (100, "exact")

    # 包含关系：要求“短串”不是无意义的片段（如纯数字、过短），避免「2」命中「6.29...」
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) < len(nb) else (nb, na)
        # 有意义的最短长度：>=3 且占长串 >=30%，且不能是纯数字
        if len(shorter) >= 3 and not shorter.isdigit() and len(shorter) >= len(longer) * 0.3:
            base = fuzz.ratio(na, nb)
            # 不要让1-2个字碰瓷拿88分：实际相似度至少达到50，且最多拿到实际分+10
            score = max(base, min(base + 10, 88)) if base >= 50 else base
            return (score, "contains")

    # 编辑距离：综合多种比，取最大值更稳健
    ratio = fuzz.ratio(na, nb)
    partial = fuzz.partial_ratio(na, nb)
    token = fuzz.token_sort_ratio(na, nb)
    token_set = fuzz.token_set_ratio(na, nb)
    score = max(ratio, partial, token, token_set)
    # 短串惩罚：一个两个字或3-4字短串不要靠 partial/token_set 碰瓷
    if min(len(na), len(nb)) < 5 and score >= 80:
        score = min(score, 40)
    return (int(round(score)), "edit_distance")


def _path_components(path: str) -> list[str]:
    """拆分路径为各级目录名（去除空段）。"""
    return [c for c in re.split(r"[\\/]", path.rstrip("/\\")) if c]


def _meaningful_components(components: list[str]) -> list[str]:
    """返回有意义的路径段：长度>=3 且非纯数字；若都没有则返回原列表。"""
    meaningful = [c for c in components if len(c) >= 3 and not c.isdigit()]
    return meaningful if meaningful else components


def match_project(
    local_name: str,
    nas_names: list[str],
    threshold: int = 80,
    top_n: int = 3,
    excluded: list[str] | None = None,
) -> list[dict]:
    """
    对一个本地项目名，在 NAS 名称列表中做模糊匹配，返回 Top-N 候选。

    :param local_name: 本地项目名（Key）
    :param nas_names:  所有 NAS 候选文件夹完整路径
    :param threshold:  匹配阈值，低于此分的候选不进入结果
    :param top_n:      返回前 N 个候选
    :param excluded:   被排除的 NAS 完整路径，直接跳过
    :return: list of {path, name, score, strategy}
    """
    excluded = excluded or []
    results: list[dict] = []
    seen: set[str] = set()
    threshold = max(threshold, 50)  # 最低50%，避免一两个字碰瓷
    for full in nas_names:
        if full in excluded:
            continue
        components = _path_components(full)
        if not components:
            continue
        # 用最后几级有意义的路径段分别比对，取最高分（避免只认叶子名）
        candidates = _meaningful_components(components)[-3:]
        best_score = 0
        best_strategy = "edit_distance"
        best_name = components[-1]
        for comp in candidates:
            sc, strat = score_pair(local_name, comp)
            if sc > best_score:
                best_score = sc
                best_strategy = strat
                best_name = comp
        if best_score >= threshold and full not in seen:
            results.append({"path": full, "name": best_name, "score": best_score, "strategy": best_strategy})
            seen.add(full)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


def decide_status(candidates: list[dict], threshold: int) -> str:
    """
    根据候选结果决定项目状态：
      - 有已确认路径 -> matched
      - 无候选 -> unmatched
      - 唯一高分候选 -> matched
      - 多个候选 / 分数落在灰色区间 -> pending
    """
    from .constants import STATUS_MATCHED, STATUS_PENDING, STATUS_UNMATCHED

    if not candidates:
        return STATUS_UNMATCHED
    top = candidates[0]
    if top["score"] >= threshold:
        if len(candidates) == 1:
            return STATUS_MATCHED
        # 多个候选且最高分达标：若第二候选明显落后(差距>=15)则视为已匹配，否则待确认
        if len(candidates) > 1 and (top["score"] - candidates[1]["score"]) >= 15:
            return STATUS_MATCHED
        return STATUS_PENDING
    return STATUS_PENDING if candidates else STATUS_UNMATCHED
