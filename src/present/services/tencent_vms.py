from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib import request, error


SERVICE = "vms"
HOST = "vms.tencentcloudapi.com"
ENDPOINT = "https://vms.tencentcloudapi.com"
VERSION = "2020-09-02"
ACTION = "SendTtsVoice"
REGION = "ap-guangzhou"


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def mask_secret(value: str) -> str:
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def credentials_status() -> Dict[str, str]:
    load_local_env()
    return {
        "secret_id": mask_secret(os.getenv("TENCENTCLOUD_SECRET_ID", "")),
        "secret_key": "已配置" if os.getenv("TENCENTCLOUD_SECRET_KEY") else "未配置",
    }


def _sign(secret_key: str, msg: str) -> bytes:
    return hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_authorization(secret_id: str, secret_key: str, payload: str, timestamp: int) -> str:
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    http_request_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{HOST}\n"
    signed_headers = "content-type;host"
    hashed_request_payload = _sha256_hex(payload)
    canonical_request = "\n".join([
        http_request_method,
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        hashed_request_payload,
    ])

    algorithm = "TC3-HMAC-SHA256"
    credential_scope = f"{date}/{SERVICE}/tc3_request"
    string_to_sign = "\n".join([
        algorithm,
        str(timestamp),
        credential_scope,
        _sha256_hex(canonical_request),
    ])

    secret_date = _sign("TC3" + secret_key, date)
    secret_service = hmac.new(secret_date, SERVICE.encode("utf-8"), hashlib.sha256).digest()
    secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def normalize_china_phone(phone: str) -> str:
    value = (phone or "").strip().replace(" ", "").replace("-", "")
    if value.startswith("+86"):
        return value
    if value.startswith("86") and len(value) == 13:
        return "+" + value
    if len(value) == 11 and value.startswith("1"):
        return "+86" + value
    return value


def send_tts_voice(
    called_number: str,
    voice_sdk_appid: str,
    template_id: str,
    template_params: List[str] | None = None,
    play_times: int = 2,
    session_context: str = "property-agent-call",
) -> Dict[str, Any]:
    load_local_env()
    secret_id = os.getenv("TENCENTCLOUD_SECRET_ID", "")
    secret_key = os.getenv("TENCENTCLOUD_SECRET_KEY", "")
    if not secret_id or not secret_key:
        raise RuntimeError("未配置腾讯云 SecretId/SecretKey。")
    if not voice_sdk_appid:
        raise RuntimeError("缺少 VoiceSdkAppid，请在腾讯云语音消息控制台创建应用后填写。")
    if not template_id:
        raise RuntimeError("缺少 TemplateId，请填写审核通过的语音通知模板 ID。")

    payload_obj = {
        "TemplateId": str(template_id),
        "TemplateParamSet": template_params or [],
        "PlayTimes": int(play_times),
        "CalledNumber": normalize_china_phone(called_number),
        "SessionContext": session_context,
        "VoiceSdkAppid": str(voice_sdk_appid),
    }
    payload = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":"))
    timestamp = int(time.time())
    authorization = build_authorization(secret_id, secret_key, payload, timestamp)

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": HOST,
        "X-TC-Action": ACTION,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": VERSION,
        "X-TC-Region": REGION,
    }

    req = request.Request(ENDPOINT, data=payload.encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": body}
        parsed["http_status"] = exc.code
        return parsed
