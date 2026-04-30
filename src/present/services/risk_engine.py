from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict, List


RISK_ORDER = {"低": 1, "中": 2, "高": 3, "待判断": 0}


@dataclass(frozen=True)
class RiskRule:
    name: str
    keywords: tuple[str, ...]
    level: str
    emergency: bool
    score: int
    action: str


DEFAULT_RULES: tuple[RiskRule, ...] = (
    RiskRule("火情/烟味", ("火灾", "起火", "冒烟", "烟味", "烧焦", "消防"), "高", True, 100, "立即通知值班室和安保到场核查，必要时拨打119。"),
    RiskRule("燃气泄漏", ("燃气", "煤气", "天然气", "刺鼻", "泄漏"), "高", True, 100, "立即提醒远离现场、开窗通风，联系燃气/消防应急力量。"),
    RiskRule("电梯困人", ("电梯困人", "困在电梯", "被困", "电梯停运"), "高", True, 95, "立即联系电梯维保和值班人员，安抚被困人员并禁止强行扒门。"),
    RiskRule("人员受伤", ("受伤", "摔倒", "昏迷", "流血", "呼吸困难", "老人倒地"), "高", True, 95, "立即安排人员到场，必要时拨打120。"),
    RiskRule("治安冲突", ("打架", "斗殴", "盗窃", "可疑人员", "抢劫", "治安"), "高", True, 90, "立即通知安保主管，必要时拨打110。"),
    RiskRule("漏水/积水", ("漏水", "渗水", "爆管", "积水", "水管"), "中", False, 60, "尽快派工程维修核查，确认是否影响电气安全和相邻住户。"),
    RiskRule("电气故障", ("停电", "跳闸", "电线", "线路", "插座", "照明"), "中", False, 60, "安排水电维修检查，优先排除触电和火灾隐患。"),
    RiskRule("电梯异常", ("电梯", "异响", "晃", "抖动"), "中", False, 65, "通知电梯维保检查，必要时临时停用并张贴提示。"),
    RiskRule("管道堵塞", ("堵塞", "下水道", "马桶", "返味"), "中", False, 45, "派管道维修人员处理，并确认影响范围。"),
    RiskRule("普通投诉", ("噪音", "投诉", "建议", "咨询", "大声聊天"), "低", False, 20, "进入常规客服工单，提醒、协调并回访。"),
)

RULE_CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "risk_rules.json"


def default_rule_dicts() -> List[Dict[str, object]]:
    return [
        {
            **asdict(rule),
            "keywords": list(rule.keywords),
            "enabled": True,
        }
        for rule in DEFAULT_RULES
    ]


def load_rule_configs() -> List[Dict[str, object]]:
    if not RULE_CONFIG_PATH.exists():
        return default_rule_dicts()

    try:
        data = json.loads(RULE_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_rule_dicts()

    if not isinstance(data, list):
        return default_rule_dicts()

    return data


def save_rule_configs(configs: List[Dict[str, object]]) -> None:
    RULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULE_CONFIG_PATH.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_rule_configs() -> None:
    save_rule_configs(default_rule_dicts())


def get_enabled_rules() -> List[RiskRule]:
    rules: List[RiskRule] = []
    for item in load_rule_configs():
        if not item.get("enabled", True):
            continue
        keywords = item.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [x.strip() for x in keywords.split(",") if x.strip()]
        rules.append(
            RiskRule(
                name=str(item.get("name", "未命名规则")),
                keywords=tuple(str(x).strip() for x in keywords if str(x).strip()),
                level=str(item.get("level", "低")),
                emergency=bool(item.get("emergency", False)),
                score=int(item.get("score", 20)),
                action=str(item.get("action", "按常规客服工单记录，必要时人工复核。")),
            )
        )
    return rules


def analyze_risk(text: str) -> Dict[str, object]:
    text = text or ""
    matched: List[RiskRule] = []
    signals: List[str] = []

    for rule in get_enabled_rules():
        hits = [word for word in rule.keywords if word in text]
        if hits:
            matched.append(rule)
            signals.extend(hits)

    if not matched:
        return {
            "risk_level": "低",
            "is_emergency": "否",
            "score": 15,
            "matched_rules": ["未命中高危规则"],
            "signals": [],
            "recommended_action": "按常规客服工单记录，必要时人工复核。",
        }

    top = max(matched, key=lambda r: (RISK_ORDER[r.level], r.score))
    score = min(100, max(r.score for r in matched) + max(0, len(set(signals)) - 1) * 3)
    return {
        "risk_level": top.level,
        "is_emergency": "是" if any(r.emergency for r in matched) else "否",
        "score": score,
        "matched_rules": [r.name for r in matched],
        "signals": sorted(set(signals)),
        "recommended_action": top.action,
    }


def merge_ai_and_rule_risk(ai_level: str, ai_emergency: str, rule_result: Dict[str, object]) -> Dict[str, object]:
    rule_level = str(rule_result.get("risk_level", "待判断"))
    final_level = ai_level if RISK_ORDER.get(ai_level, 0) >= RISK_ORDER.get(rule_level, 0) else rule_level
    final_emergency = "是" if ai_emergency == "是" or rule_result.get("is_emergency") == "是" else "否"
    return {
        "risk_level": final_level,
        "is_emergency": final_emergency,
        "source": "规则+AI综合判断",
    }
