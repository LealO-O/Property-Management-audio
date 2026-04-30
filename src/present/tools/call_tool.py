# src/present/tools/call_tool.py

from crewai.tools import tool


@tool("emergency_call_tool")
def emergency_call_tool(scene: str, address: str, contact: str, details: str) -> str:
    """
    紧急求援电话话术生成工具。
    用于在发生火灾、人员受伤、燃气泄漏、电梯困人等紧急事件时，
    生成可直接拨打给119/120/110/物业值班室的话术内容。
    """
    scene = (scene or "").strip()
    address = (address or "").strip()
    contact = (contact or "").strip()
    details = (details or "").strip()

    if not scene:
        scene = "紧急异常事件"
    if not address:
        address = "地址待进一步确认"
    if not contact:
        contact = "现场联系人待确认"
    if not details:
        details = "现场细节待进一步补充"

    script = f"""
【紧急外呼话术】
您好，这里是物业服务中心，现在报告一起紧急事件。

【事件类型】
{scene}

【事发地点】
{address}

【现场联系人】
{contact}

【详细情况】
{details}

请立即安排人员前往处理，谢谢。
""".strip()

    return script


@tool("suggest_emergency_phone_tool")
def suggest_emergency_phone_tool(scene: str) -> str:
    """
    根据事件类型建议优先拨打的电话。
    """
    scene = (scene or "").strip()

    if any(k in scene for k in ["火灾", "冒烟", "起火", "燃气", "煤气"]):
        return "建议优先拨打：119（火警）+ 物业值班电话"
    if any(k in scene for k in ["受伤", "昏迷", "摔倒", "流血", "心脏", "呼吸困难"]):
        return "建议优先拨打：120（急救）+ 物业值班电话"
    if any(k in scene for k in ["打架", "盗窃", "抢劫", "可疑人员", "治安"]):
        return "建议优先拨打：110（报警）+ 物业值班电话"
    if any(k in scene for k in ["电梯困人", "停电", "漏水", "爆管", "门禁故障"]):
        return "建议优先拨打：物业值班电话 / 工程值班电话"
    return "建议优先拨打：物业值班电话，并根据现场情况联系 110 / 119 / 120"