"""两条冷链路线的经验分布与温区暴露复核。"""
import math
import random
import numpy as np
from scipy import stats

MAX_GAP_DEFAULT, MAX_GAP_MIN, MAX_GAP_MAX = 4, 1, 120


def metadata():
    return {"name": "冷链温区偏离调查", "short": "cold-excursion", "tagline": "不只看最高温，核对整条路线的温度分布。",
            "client": "澄源冷运 · 18 名调度员，生物试剂城配线路试运行组", "workflow": "调度把温度记录贴到 Excel，以最高温决定是否调查路线。",
            "pains": ["单个峰值无法说明持续暴露", "不同线路分布不便比较", "不等间隔采样下，测温点占比会误判暴露时长", "阈值调整后需手工重算"], "upstream": "温度记录器导出的 CY_route_temperature.csv", "downstream": "冷运质控经理据分布差异安排包装复核",
            "entities": ["路线温度样本", "温区调查", "质控分发简报"], "dataset_name": "沪东 A / B 路线 · 240 个测温点",
            "columns": [{"key": "sample", "label": "采样点", "type": "string"}, {"key": "route", "label": "路线", "type": "string"}, {"key": "minute", "label": "发车后分钟", "type": "number"}, {"key": "temperature", "label": "温度 °C", "type": "number"}],
            "parameters": [{"key": "upper", "label": "温区上界 °C", "type": "number", "default": 8, "min": 2, "max": 15}, {"key": "alpha", "label": "显著性水平", "type": "select", "default": "0.05", "options": [{"value": "0.01", "label": "0.01"}, {"value": "0.05", "label": "0.05"}, {"value": "0.1", "label": "0.10"}]}, {"key": "max_gap", "label": "间隔上限 分钟", "type": "number", "default": MAX_GAP_DEFAULT, "min": MAX_GAP_MIN, "max": MAX_GAP_MAX}],
            "workbench_title": "温度分布比对", "action_label": "执行 KS 与超温复核", "unit": "°C", "accent": "oklch(48% 0.08 184)", "style": "coldroom",
            "seed_story": ["08:00 导入 CY_route_temperature.csv，沪东 A/B 各 120 点。", "08:15 核对采样间隔为 2 分钟。", "08:20 补传迟到的乱序记录：按分钟归位，相同记录去重，冲突整批拒绝。", "08:30 质控将温区上界设为 8°C。", "08:35 执行双样本 KS 比较，打开经验分布曲线。", "08:50 查看两路线超温比例、P95 与超温时长占比。", "09:10 将上界设为 7°C，评估更严格口径。", "09:30 导出调查明细，安排 B 线保温包装复核。"],
            "method": "KS 统计量 D=sup|F_A(t)−F_B(t)|，双侧双样本检验；超温率=count(T>上界)/有效采样数；ECDF 按同一温度网格计算。按时间调查：记录按分钟归位，同路线同分钟的相同记录只算一次；区间 [t_i, t_i+1) 沿用前点温度，间隔超过上限的整段记缺测，末点不外推；超温时长占比=超温时长÷有效时长。",
            "limitations": ["连续采样点可能自相关，KS p 值仅作筛查参考", "比例是采样点比例，未估算货物核心温度", "缺测时段不假设温度状态，不计入有效时长", "不能据统计结果直接判定试剂可用性"]}


def seed_records():
    rng = random.Random(1002)
    rows = []
    for route, offset in [("沪东 A", 0), ("沪东 B", 1.15)]:
        for i in range(120):
            temp = 5.4 + offset + .6 * math.sin(i / 11) + rng.gauss(0, .6)
            if route == "沪东 B" and 56 <= i <= 72:
                temp += 1.8
            rows.append({"sample": f"{route[-1]}-{i+1:03}", "route": route, "minute": i * 2, "temperature": round(temp, 3)})
    return rows


def _time_investigation(records, upper, max_gap):
    """按时间归并：相同记录只算一次，冲突拒绝；前点温度沿用至下一点，间隔超限整段记缺测，末点不外推。"""
    timelines = {}
    for r in records:
        try:
            name, minute, temp = str(r["route"]), float(r["minute"]), float(r["temperature"])
            if not (math.isfinite(minute) and math.isfinite(temp)):
                raise ValueError()
        except (TypeError, ValueError, KeyError):
            raise ValueError("每点须有路线、有限的发车后分钟和温度数值")
        seen = timelines.setdefault(name, {})
        if minute in seen:
            if seen[minute] == temp:
                continue  # 相同记录只算一次
            raise ValueError(f"{name} 在 {minute:g} 分钟存在冲突温度记录，无法归并时间轴")
        seen[minute] = temp
    rows = []
    for name in sorted(timelines):
        points = sorted(timelines[name].items())
        valid = missing = over = 0.0
        for (m0, t0), (m1, _) in zip(points, points[1:]):
            gap = m1 - m0
            if gap > max_gap:
                missing += gap
            else:
                valid += gap
                if t0 > upper:
                    over += gap
        if valid <= 0:
            raise ValueError(f"{name} 在间隔上限 {max_gap:g} 分钟下有效时长为 0，请放宽间隔上限或检查数据")
        rows.append({"route": name, "points": len(points), "valid": round(valid, 3), "missing": round(missing, 3), "over": round(over, 3), "ratio": round(over / valid * 100, 3)})
    return rows


def analyze(records, params):
    try:
        upper, alpha = float(params.get("upper", 8)), float(params.get("alpha", .05))
        max_gap = float(params.get("max_gap", MAX_GAP_DEFAULT))
    except (ValueError, TypeError):
        raise ValueError("温区、显著性水平和间隔上限须为数值")
    if not math.isfinite(upper) or not 2 <= upper <= 15 or alpha not in (.01, .05, .1):
        raise ValueError("上界范围 2–15°C，显著性水平只接受 0.01/0.05/0.1")
    if not math.isfinite(max_gap) or not MAX_GAP_MIN <= max_gap <= MAX_GAP_MAX:
        raise ValueError(f"间隔上限范围 {MAX_GAP_MIN}–{MAX_GAP_MAX} 分钟")
    grouped = {}
    for r in records:
        try:
            name, val = str(r["route"]), float(r["temperature"])
            if not math.isfinite(val):
                raise ValueError()
            grouped.setdefault(name, []).append(val)
        except (TypeError, ValueError, KeyError):
            raise ValueError("每点须有路线和有限温度数值")
    if len(grouped) != 2 or any(len(v) < 10 for v in grouped.values()):
        raise ValueError("恰需两条路线，每条至少 10 个测温点")
    names = sorted(grouped)
    a, b = [np.array(grouped[n]) for n in names]
    ks = stats.ks_2samp(a, b, alternative="two-sided", method="auto")
    grid = np.linspace(min(float(a.min()), float(b.min())), max(float(a.max()), float(b.max())), 25)
    rows = [{"route": n, "count": len(grouped[n]), "mean": round(float(np.mean(grouped[n])), 3), "p95": round(float(np.quantile(grouped[n], .95)), 3), "over": int(sum(t > upper for t in grouped[n])), "rate": round(sum(t > upper for t in grouped[n]) / len(grouped[n]) * 100, 3)} for n in names]
    verdict = "存在分布差异" if float(ks.pvalue) < alpha else "未检出分布差异"
    time_rows = _time_investigation(records, upper, max_gap)
    lead = max(time_rows, key=lambda r: r["ratio"])
    time_findings = [f"{r['route']} 有效 {r['valid']:g} 分钟、缺测 {r['missing']:g} 分钟；超温 {r['over']:g} 分钟，占有效时长 {r['ratio']:g}%。" for r in time_rows]
    time_findings.append(f"按时间口径 {lead['route']} 的超温时长占比更高，优先安排其暴露复核。" if lead["ratio"] > min(r["ratio"] for r in time_rows) else "按时间口径两路线超温时长占比相同。")
    time_findings.append(f"缺测时段不假设温度状态；末点之后不外推，间隔上限 {max_gap:g} 分钟。")
    return {"summary": f"{names[0]} 与 {names[1]} 的 KS D={ks.statistic:.3f}，在 α={alpha:g} 下{verdict}。",
            "metrics": [{"label": "KS 距离 D", "value": round(float(ks.statistic), 5)}, {"label": "双侧 p 值", "value": float(f"{ks.pvalue:.6g}")}, {"label": "路线 B 超温率", "value": rows[1]["rate"], "unit": "%"}, {"label": "温区上界", "value": upper, "unit": "°C"}],
            "table": {"columns": [{"key": "route", "label": "路线"}, {"key": "count", "label": "采样点"}, {"key": "mean", "label": "均温 °C"}, {"key": "p95", "label": "P95 °C"}, {"key": "over", "label": "超温点"}, {"key": "rate", "label": "超温率 %"}], "rows": rows},
            "chart": {"type": "line", "labels": [f"{x:.2f}°C" for x in grid], "series": [{"name": n + " 累积比例%", "values": [round(sum(v <= x for v in grouped[n]) / len(grouped[n]) * 100, 3) for x in grid]} for n in names]},
            "time_table": {"columns": [{"key": "route", "label": "路线"}, {"key": "points", "label": "归并采样点"}, {"key": "valid", "label": "有效时长 分"}, {"key": "missing", "label": "缺测时长 分"}, {"key": "over", "label": "超温时长 分"}, {"key": "ratio", "label": "超温占有效 %"}], "rows": time_rows},
            "time_chart": {"type": "bar", "labels": ["有效时长", "超温时长", "缺测时长"], "series": [{"name": r["route"], "values": [r["valid"], r["over"], r["missing"]]} for r in time_rows]},
            "time_findings": time_findings,
            "findings": [f"{n} 超温点 {r['over']}/{r['count']}，比例 {r['rate']:.2f}%。" for n, r in zip(names, rows)] + ["统计差异仅定位调查对象；请结合门开记录和独立运输批次复核。"],
            "method": metadata()["method"], "warnings": ["同一路线的连续采样存在自相关，不能把 p 值作为独立批次证据。"]}
