# -*- coding: utf-8 -*-
"""
MediaNexus - 数据模型
提供类型化的项目模型，替代裸 dict 访问，在边界处做校验。

用法：
    # 从配置读取时转换
    proj = Project.from_dict(raw_dict)

    # 写回配置时转换
    config_manager.upsert_project(proj.to_dict())

    # 也可以直接构造
    proj = Project(local_name="...", name="我的项目")
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# 合法的项目状态值
VALID_STATUS = frozenset({"matched", "pending", "unmatched", "none", ""})


@dataclass
class Project:
    """项目实体 — 类型化替代裸 dict。

    Attributes:
        local_name: 内部唯一键（历史字段名，通常等于服务器路径，不是显示名）
        name: 项目显示名（用户可见）
        local_path: 本地目录（可为空）
        nas_candidates: 匹配候选服务器路径列表
        confirmed_nas_path: 已确认的服务器目录
        status: 匹配状态 (matched / pending / unmatched / none)
        last_sync: 最后同步时间 ISO 格式
    """

    local_name: str
    name: str = ""
    local_path: str = ""
    nas_candidates: list[str] = field(default_factory=list)
    confirmed_nas_path: str = ""
    status: str = ""
    last_sync: str = ""

    def __post_init__(self):
        """校验关键字段。"""
        if not self.local_name:
            raise ValueError("Project.local_name 不能为空（它是内部唯一键）")
        if self.status not in VALID_STATUS:
            raise ValueError(
                f"Project.status 值非法: {self.status!r}，"
                f"合法值: {sorted(VALID_STATUS)}"
            )
        # nas_candidates 必须是列表
        if not isinstance(self.nas_candidates, list):
            self.nas_candidates = list(self.nas_candidates)

    @property
    def display_name(self) -> str:
        """用户可见的显示名：优先 name，fallback 到 local_name 末段。"""
        if self.name:
            return self.name
        # 从路径中提取末段作为 fallback 显示名
        import os
        return os.path.basename(self.local_name.rstrip("/\\")) or self.local_name

    @property
    def is_matched(self) -> bool:
        return self.status == "matched"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        """从配置中的裸 dict 构造 Project（容忍缺失字段）。"""
        return cls(
            local_name=data.get("local_name", ""),
            name=data.get("name", ""),
            local_path=data.get("local_path", ""),
            nas_candidates=data.get("nas_candidates", []),
            confirmed_nas_path=data.get("confirmed_nas_path", ""),
            status=data.get("status", ""),
            last_sync=data.get("last_sync", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为可 JSON 序列化的 dict（用于写回配置）。"""
        return asdict(self)

    def merge_dict(self, data: dict[str, Any]) -> "Project":
        """将外部 dict 中的非空字段合并到当前实例（用于增量更新）。"""
        for key in ("name", "local_path", "nas_candidates",
                    "confirmed_nas_path", "status", "last_sync"):
            if key in data and data[key] is not None:
                setattr(self, key, data[key])
        # 重新校验
        self.__post_init__()
        return self
