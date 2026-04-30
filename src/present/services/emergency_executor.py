import json
from typing import Any, Dict, List, Optional

from present.tools.call_tool import emergency_call_tool


class EmergencyExecutor:
    """
    应急执行器：
    - 根据 emergency_response_task 的结果，顺序执行外呼
    - 若未提供电话号码，则跳过
    - 返回执行记录，供主程序打印或写回工单
    """

    def __init__(self, phone_book: Optional[Dict[str, str]] = None) -> None:
        self.phone_book = phone_book or {}

    def resolve_phone(self, role: str) -> str:
        return self.phone_book.get(role, "")

    def trigger_calls(self, event_id: str, emergency_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not emergency_result:
            return []

        if not emergency_result.get("emergency_required", False):
            return []

        contacts = emergency_result.get("contacts_to_call", [])
        message = emergency_result.get("emergency_call_script", "")
        call_records: List[Dict[str, Any]] = []

        sorted_contacts = sorted(contacts, key=lambda x: x.get("priority", 999))

        for contact in sorted_contacts:
            role = contact.get("role", "未知角色")
            phone_number = contact.get("phone", "") or self.resolve_phone(role)

            if not phone_number:
                call_records.append(
                    {
                        "role": role,
                        "success": False,
                        "reason": "未找到电话号码，跳过外呼"
                    }
                )
                continue

            raw_result = emergency_call_tool.run(
                phone_number=phone_number,
                message=message,
                event_id=event_id,
                contact_role=role
            )

            try:
                parsed = json.loads(raw_result)
            except json.JSONDecodeError:
                parsed = {
                    "success": False,
                    "raw_result": raw_result
                }

            call_records.append(
                {
                    "role": role,
                    "phone_number": phone_number,
                    "result": parsed
                }
            )

        return call_records