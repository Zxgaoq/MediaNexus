"""
一致性校验模块（精简版）
仅对比 5 项核心指标：分辨率、帧率、视频格式(封装)、视频编码、音频编码
"""
import logging

logger = logging.getLogger("VideoQC.Consistency")


class ConsistencyChecker:
    """视频参数一致性校验器 — 精简 5 项"""

    # 仅检查这 5 项核心参数
    # (取值函数, 标签)
    CHECKS = [
        ("container",    "视频格式",   lambda p: p.get("container", "未知")),
        ("video_codec",  "视频编码",   lambda p: (p.get("video") or {}).get("codec", "未知")),
        ("resolution",   "分辨率",     lambda p: (p.get("video") or {}).get("resolution", "未知")),
        ("fps",          "帧率",       lambda p: (p.get("video") or {}).get("fps", "未知")),
        ("audio_codec",  "音频编码",   lambda p: (p.get("audio") or {}).get("codec", "未知")),
    ]

    @staticmethod
    def check_against_baseline(probe_results, baseline_index=0):
        """
        以第一个文件为基准，对比所有文件的 5 项核心参数。

        Returns:
            dict: {
                "baseline_file": str,
                "files": [{filename, inconsistencies, is_consistent}],
                "overall_consistent": bool,
                "all_param_values": {param_key: {label, values}},  # 供 UI 展示
            }
        """
        if not probe_results or baseline_index >= len(probe_results):
            return {"error": "无效基准", "files": [], "overall_consistent": False,
                    "all_param_values": {}}

        baseline = probe_results[baseline_index]
        logger.info(f"一致性基准: {baseline['filename']}")

        # 先构建全量参数矩阵（所有文件、所有 5 项参数）
        all_param_values = {}
        for param_key, label, getter in ConsistencyChecker.CHECKS:
            vals = {}
            for probe in probe_results:
                vals[probe["filename"]] = str(getter(probe))
            all_param_values[param_key] = {"label": label, "values": vals}

        # 逐文件对比
        results = []
        all_inconsistent = 0

        for i, probe in enumerate(probe_results):
            if i == baseline_index:
                results.append({
                    "filename": probe["filename"],
                    "filepath": probe["filepath"],
                    "is_baseline": True,
                    "inconsistencies": [],
                    "is_consistent": True,
                })
                continue

            inconsistencies = []
            for param_key, label, getter in ConsistencyChecker.CHECKS:
                expected = getter(baseline)
                actual = getter(probe)
                if expected != actual:
                    inconsistencies.append({
                        "param": label,
                        "key": param_key,
                        "expected": str(expected),
                        "actual": str(actual),
                        "severity": "错误",
                    })

            if inconsistencies:
                all_inconsistent += 1

            results.append({
                "filename": probe["filename"],
                "filepath": probe["filepath"],
                "inconsistencies": inconsistencies,
                "is_consistent": len(inconsistencies) == 0,
            })

        overall = all_inconsistent == 0

        return {
            "baseline_file": baseline["filename"],
            "files": results,
            "overall_consistent": overall,
            "all_param_values": all_param_values,
        }

