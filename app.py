import sys
import os
import re
import time
import random
import tempfile
from datetime import datetime
from typing import Dict, Any

import streamlit as st


def load_cloud_secrets_to_env():
    for key in [
        "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "SERPER_API_KEY",
        "TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY", "TENCENT_VMS_REGION",
    ]:
        try:
            value = st.secrets.get(key)
        except Exception:
            value = None
        if value and not os.getenv(key):
            os.environ[key] = str(value)

load_cloud_secrets_to_env()
from faster_whisper import WhisperModel

sys.path.append("src")
from present.crew import Present
from present.services.risk_engine import analyze_risk, load_rule_configs, merge_ai_and_rule_risk, reset_rule_configs, save_rule_configs
from present.services.storage import load_state, save_state
from present.services.tencent_vms import credentials_status, send_tts_voice


# =========================
# 页面配置
# =========================
st.set_page_config(
    page_title="智联物业 Agent：来电智处助手",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
.block-container {padding-top: 1.2rem;}
.card {
    background: white;
    border: 1px solid #d8ecff;
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 4px 16px rgba(30, 100, 200, 0.08);
}
.title-card {
    background: linear-gradient(135deg, #eef7ff, #ffffff);
    border: 1px solid #bfe0ff;
    border-radius: 22px;
    padding: 24px;
    margin-bottom: 18px;
}
.risk-high {
    background:#fff1f0;
    border:1px solid #ffb3ad;
    color:#b42318;
    padding:14px;
    border-radius:16px;
    font-weight:800;
}
.risk-mid {
    background:#fff8e6;
    border:1px solid #f5d97b;
    color:#9a6700;
    padding:14px;
    border-radius:16px;
    font-weight:800;
}
.risk-low {
    background:#ecfdf3;
    border:1px solid #a6f4c5;
    color:#067647;
    padding:14px;
    border-radius:16px;
    font-weight:800;
}
.tag {
    display:inline-block;
    padding:5px 11px;
    border-radius:999px;
    background:#e8f3ff;
    border:1px solid #bfdfff;
    color:#175cd3;
    font-size:12px;
    margin-right:8px;
}
.timeline-item {
    border-left: 3px solid #2e90fa;
    padding: 0 0 14px 14px;
    margin-left: 6px;
}
.timeline-time {
    color:#175cd3;
    font-weight:800;
    font-size:13px;
}
.timeline-title {font-weight:800;}
.rule-box {
    background:#f8fbff;
    border:1px solid #cfe8ff;
    border-radius:14px;
    padding:14px;
    margin:8px 0;
}
.live-line {
    border-left:3px solid #12b76a;
    background:#f6fffb;
    padding:9px 12px;
    margin:8px 0;
    border-radius:10px;
}
.live-risk {
    background:#fff8e6;
    border:1px solid #f5d97b;
    color:#7a4b00;
    padding:10px;
    border-radius:12px;
    font-weight:700;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# =========================
# 基础数据
# =========================
EMERGENCY_CONTACTS = {
    "物业值班室": "13800001111",
    "安保主管": "13900002222",
    "消防联动联系人": "119",
}

REPAIR_STAFF = {
    "安保主管": {
        "role": "应急处置",
        "phone": "13900002222",
        "skills": ["火灾", "烟味", "冒烟", "燃气", "治安", "应急", "起火"],
    },
    "物业值班室": {
        "role": "值班联动",
        "phone": "13800001111",
        "skills": ["火灾", "烟味", "燃气", "电梯困人", "受伤", "应急"],
    },
    "张师傅": {
        "role": "水电维修",
        "phone": "13800008881",
        "skills": ["漏水", "停电", "照明", "开关", "线路"],
    },
    "李师傅": {
        "role": "管道维修",
        "phone": "13800008882",
        "skills": ["堵塞", "下水道", "水管", "渗水", "马桶"],
    },
    "王师傅": {
        "role": "综合维修",
        "phone": "13800008883",
        "skills": ["门锁", "窗户", "墙面", "普通维修", "破损"],
    },
    "赵师傅": {
        "role": "电梯维保",
        "phone": "13800008884",
        "skills": ["电梯", "困人", "异响", "停运", "晃"],
    },
}

DEMO_CASES = {
    "疑似火灾": "喂你好，我是3号楼2单元的住户，现在楼道里有很重的烟味，好像是从楼下传上来的，有点呛人，不确定是不是起火了，你们能赶紧来看一下吗？",
    "漏水维修": "你好，我是5号楼1单元802的住户，厨房水管一直在漏水，地面已经有积水了，希望物业尽快安排师傅来看一下。",
    "电梯故障": "你好，2号楼电梯今天一直有异响，而且运行的时候有点晃，麻烦安排维保人员检查一下。",
    "普通投诉建议": "你好，小区晚上楼下有人大声聊天，影响休息，希望物业能提醒一下。",
}


INCIDENT_PLANS = {
    "火情/烟味": {
        "title": "火情/烟味应急预案",
        "level": "高",
        "owner": "物业值班室 + 安保主管",
        "steps": ["确认具体楼栋、单元、楼层和烟味来源", "提醒来电人远离烟源并保持电话畅通", "通知安保和值班人员到场核查", "必要时拨打119并同步疏散周边住户", "记录处置过程并完成回访归档"],
    },
    "燃气泄漏": {
        "title": "燃气泄漏应急预案",
        "level": "高",
        "owner": "物业值班室 + 燃气/消防联动",
        "steps": ["提醒住户不要开关电器或使用明火", "开窗通风并撤离危险区域", "联系燃气公司和消防应急力量", "安保到场设置警戒", "事件解除后回访并归档"],
    },
    "电梯困人": {
        "title": "电梯困人应急预案",
        "level": "高",
        "owner": "电梯维保 + 安保主管",
        "steps": ["确认电梯编号、楼层和被困人数", "安抚被困人员，禁止强行扒门", "立即联系电梯维保到场", "安排安保现场值守", "救援完成后记录维保报告并回访"],
    },
    "电梯异常": {
        "title": "电梯异常处置预案",
        "level": "中",
        "owner": "电梯维保",
        "steps": ["确认楼栋、电梯编号和异常表现", "必要时临时停梯并张贴提示", "联系维保单位检查", "记录故障原因和修复结果", "恢复运行后通知住户并回访"],
    },
    "漏水/积水": {
        "title": "漏水/积水维修预案",
        "level": "中",
        "owner": "工程维修部",
        "steps": ["确认房号、漏水位置和是否持续扩大", "提醒关闭水阀并远离带电设备", "派工程维修上门处理", "确认是否影响楼下或公共区域", "维修完成后回访并归档"],
    },
    "电气故障": {
        "title": "电气故障处置预案",
        "level": "中",
        "owner": "水电维修",
        "steps": ["确认故障位置和影响范围", "提醒住户避免自行拆修", "派水电维修检查线路", "排除触电和火灾隐患", "恢复后记录原因并回访"],
    },
    "普通投诉": {
        "title": "普通投诉协调预案",
        "level": "低",
        "owner": "客服专员",
        "steps": ["记录投诉对象、时间和地点", "客服或管家进行提醒协调", "必要时通知安保巡查", "记录处理结果", "在约定时间内回访"],
    },
}




REALTIME_STREAMING_ARCH = {
    "接入方式": [
        "呼叫中心 SIP/CTI 平台把电话音频按 1~3 秒切片推送到后端 WebSocket",
        "WebRTC 坐席页面直接采集麦克风/通话轨道并上传音频帧",
        "电话录音兜底：通话结束后上传完整录音做补识别和复核",
    ],
    "服务端流程": [
        "stream_id 标识一通电话，会话级缓存 caller、坐席、开始时间和转写片段",
        "每个 audio_chunk 进入 ASR 队列，输出 partial_text 和 confidence",
        "partial_text 立即进入规则引擎，命中高风险词时推送实时预警",
        "通话结束后合并全文，交给多 Agent 生成纪要、工单、追问和预案",
    ],
    "生产替换点": [
        "当前演示按钮 = 模拟 audio_chunk 到达",
        "真实部署时替换为 /ws/call-stream WebSocket 音频流",
        "当前本地 Whisper = 可替换为企业 ASR、云 ASR 或 faster-whisper GPU 服务",
        "当前 SQLite = 可替换为 MySQL/PostgreSQL + 对象存储保存录音",
    ],
}

STREAMING_CONTRACT = """{
  \"event\": \"audio_chunk\",
  \"stream_id\": \"call-20260425-0001\",
  \"caller\": \"138****5678\",
  \"seq\": 12,
  \"sample_rate\": 16000,
  \"format\": \"pcm_s16le\",
  \"audio_base64\": \"...\"
}

{
  \"event\": \"partial_transcript\",
  \"stream_id\": \"call-20260425-0001\",
  \"seq\": 12,
  \"text\": \"楼道里有很重的烟味\",
  \"confidence\": 0.91,
  \"risk_preview\": {
    \"risk_level\": \"高\",
    \"is_emergency\": \"是\",
    \"matched_rules\": [\"火情/烟味\"]
  }
}"""

# =========================
# CrewAI 调用
# =========================
def call_crew(user_input: str) -> str:
    result = Present().crew().kickoff(inputs={"input": user_input})
    return str(result)


# =========================
# 语音转文本
# =========================
@st.cache_resource
def load_asr_model():
    return WhisperModel("base", device="cpu", compute_type="int8")


def real_asr(audio_file) -> str:
    suffix = ".wav"

    if hasattr(audio_file, "name") and "." in audio_file.name:
        suffix = "." + audio_file.name.split(".")[-1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_file.getvalue())
        tmp_path = tmp.name

    model = load_asr_model()

    segments, info = model.transcribe(
        tmp_path,
        language="zh",
        beam_size=5,
        vad_filter=True,
    )

    text = "".join([seg.text for seg in segments]).strip()

    if not text:
        return "未识别到有效语音，请换一段更清晰的中文录音。"

    return text


# =========================
# 结果解析
# =========================
def safe_extract(pattern: str, text: str, default: str = "未提取到") -> str:
    m = re.search(pattern, text, re.S)
    return m.group(1).strip() if m else default


def extract_risk_level(text: str) -> str:
    for p in [r"风险等级[：:\*\s]*([高中低])", r"紧急程度[：:\*\s]*([高中低])"]:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return "待判断"


def extract_emergency(text: str) -> str:
    for p in [r"是否紧急[：:\*\s]*([是否])", r"是否属于紧急事件[：:\*\s]*([是否])"]:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return "待判断"


def section_between(text: str, start_patterns: list[str], end_patterns: list[str], default: str = "未提取到") -> str:
    start_match = None
    for pattern in start_patterns:
        match = re.search(pattern, text, re.S)
        if match and (start_match is None or match.start() < start_match.start()):
            start_match = match

    if not start_match:
        return default

    start = start_match.end()
    end = len(text)
    for pattern in end_patterns:
        match = re.search(pattern, text[start:], re.S)
        if match:
            end = min(end, start + match.start())

    value = text[start:end].strip(" \n\r\t-*：:")
    return value or default


def parse_result(raw_text: str) -> Dict[str, Any]:
    h1 = [r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*\*)?\s*1\.?\s*通话纪要\s*(?:\*\*)?", r"(?:^|\n)\s*(?:\*\*)?\s*通话纪要\s*(?:\*\*)?"]
    h2 = [r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*\*)?\s*2\.?\s*风险提示\s*(?:\*\*)?", r"(?:^|\n)\s*(?:\*\*)?\s*风险提示\s*(?:\*\*)?"]
    h3 = [r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*\*)?\s*3\.?\s*工单待办\s*(?:\*\*)?", r"(?:^|\n)\s*(?:\*\*)?\s*工单待办\s*(?:\*\*)?"]
    h4 = [r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*\*)?\s*4\.?\s*建议追问\s*(?:\*\*)?", r"(?:^|\n)\s*(?:\*\*)?\s*建议追问\s*(?:\*\*)?"]
    h5 = [r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:\*\*)?\s*5\.?\s*应急联动建议\s*(?:\*\*)?", r"(?:^|\n)\s*(?:\*\*)?\s*应急联动建议\s*(?:\*\*)?"]

    return {
        "risk_level": extract_risk_level(raw_text),
        "is_emergency": extract_emergency(raw_text),
        "call_summary": section_between(raw_text, h1, h2, raw_text),
        "risk_summary": section_between(raw_text, h2, h3),
        "workorder": section_between(raw_text, h3, h4),
        "questions": section_between(raw_text, h4, h5),
        "emergency_block": section_between(raw_text, h5, [], "无"),
        "raw_text": raw_text,
    }



def split_live_demo(text: str) -> list[str]:
    chunks = [x.strip() for x in re.split(r"[，。！？；,.!?;]+", text) if x.strip()]
    return chunks or [text]


def append_live_chunk(chunk: str) -> None:
    chunk = chunk.strip()
    if not chunk:
        return

    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.live_call_chunks.append({"time": now, "text": chunk})
    transcript = "，".join(item["text"] for item in st.session_state.live_call_chunks)
    st.session_state.transcript_text = transcript
    st.session_state.live_partial_text = ""


def reset_live_call() -> None:
    st.session_state.live_call_chunks = []
    st.session_state.live_demo_chunks = []
    st.session_state.live_demo_index = 0
    st.session_state.live_partial_text = ""
    st.session_state.transcript_text = ""


def render_live_transcript() -> None:
    if not st.session_state.live_call_chunks:
        st.info("接听后可逐段同步识别，识别内容会实时汇总到右侧文本框。")
        return

    for item in st.session_state.live_call_chunks[-6:]:
        st.markdown(
            f'<div class="live-line"><b>{item["time"]}</b>　{item["text"]}</div>',
            unsafe_allow_html=True,
        )


def render_live_risk_preview(text_value: str) -> None:
    if not text_value.strip():
        return

    rule = analyze_risk(text_value)
    st.markdown(
        f'<div class="live-risk">实时风险预警：{rule["risk_level"]}风险｜是否紧急：{rule["is_emergency"]}｜命中：{", ".join(rule["matched_rules"])}</div>',
        unsafe_allow_html=True,
    )
    if rule.get("signals"):
        st.caption("关键词信号：" + "、".join(rule["signals"]))


def persist_runtime_state() -> None:
    save_state("workorder_pool", st.session_state.get("workorder_pool", []))
    save_state("call_logs", st.session_state.get("call_logs", []))
    if "result" in st.session_state:
        save_state("last_result", st.session_state.result)
    if "last_input" in st.session_state:
        save_state("last_input", st.session_state.last_input)


def build_event_timeline(user_input: str, result: Dict[str, Any]) -> list[Dict[str, str]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_high = result.get("risk_level") == "高" or result.get("is_emergency") == "是"
    dispatch = "进入应急外呼确认" if is_high else "进入后台工单池待派单"
    action = "人工确认后通知值班室/安保/外部应急" if is_high else "按优先级自动排序并推荐维修人员"
    return [
        {"time": now, "title": "来电内容接入", "detail": user_input[:120] + ("..." if len(user_input) > 120 else "")},
        {"time": now, "title": "语音/文本完成标准化", "detail": "已形成可供多 Agent 分析的来电文本。"},
        {"time": now, "title": "规则引擎完成兜底判断", "detail": result.get("rule_risk", {}).get("recommended_action", "按常规流程处理。")},
        {"time": now, "title": "多 Agent 完成闭环分析", "detail": f"风险等级：{result.get('risk_level')}；是否紧急：{result.get('is_emergency')}。"},
        {"time": now, "title": dispatch, "detail": action},
    ]


def render_timeline(timeline: list[Dict[str, str]]) -> None:
    for item in timeline:
        st.markdown(
            f"""
            <div class="timeline-item">
                <div class="timeline-time">{item.get('time', '')}</div>
                <div class="timeline-title">{item.get('title', '')}</div>
                <div>{item.get('detail', '')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_rule_explain(result: Dict[str, Any]) -> None:
    rule = result.get("rule_risk", {})
    st.markdown('<div class="rule-box">', unsafe_allow_html=True)
    st.markdown("**规则兜底判断**")
    st.write(f"命中规则：{', '.join(rule.get('matched_rules', [])) or '无'}")
    st.write(f"关键词信号：{', '.join(rule.get('signals', [])) or '无'}")
    st.write(f"规则风险分：{rule.get('score', 0)}")
    st.write(f"建议动作：{rule.get('recommended_action', '按常规流程处理。')}")
    st.caption("比赛说明：规则引擎负责安全兜底，大模型负责复杂语义理解，最终由人工确认执行。")
    st.markdown("</div>", unsafe_allow_html=True)



def get_matched_plan(result: Dict[str, Any]) -> Dict[str, Any]:
    for name in result.get("rule_risk", {}).get("matched_rules", []):
        if name in INCIDENT_PLANS:
            return INCIDENT_PLANS[name]
    return INCIDENT_PLANS["普通投诉"]


def render_plan_card(plan: Dict[str, Any]) -> None:
    st.markdown('<div class="rule-box">', unsafe_allow_html=True)
    st.markdown(f"**{plan['title']}**")
    st.write(f"预案等级：{plan['level']}｜责任角色：{plan['owner']}")
    for idx, step in enumerate(plan["steps"], 1):
        st.write(f"{idx}. {step}")
    st.markdown("</div>", unsafe_allow_html=True)


def confirm_emergency_action(content: str, confirmed_by: str, action: str) -> bool:
    for item in st.session_state.workorder_pool:
        if item.get("content") == content and item.get("order_type") == "应急事件工单" and item.get("status") not in ["已完成", "已回访"]:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item["status"] = "应急联动确认"
            item["confirmed_by"] = confirmed_by
            item["confirmed_at"] = now
            item["confirmed_action"] = action
            item.setdefault("logs", []).append(f"{now} {confirmed_by} 已确认：{action}")
            persist_runtime_state()
            return True
    return False



def render_evidence_chain(result: Dict[str, Any]) -> None:
    rule = result.get("rule_risk", {})
    plan = get_matched_plan(result)
    st.markdown("**可信证据链**")
    st.write(f"原始输入：{st.session_state.get('last_input', '待确认')[:160]}")
    st.write(f"关键词证据：{', '.join(rule.get('signals', [])) or '无'}")
    st.write(f"规则命中：{', '.join(rule.get('matched_rules', [])) or '无'}")
    st.write(f"AI 原始判断：{result.get('ai_risk_level', result.get('risk_level'))}/{result.get('ai_is_emergency', result.get('is_emergency'))}")
    st.write(f"综合判断：{result.get('risk_level')}/{result.get('is_emergency')}")
    st.write(f"匹配预案：{plan.get('title', '待确认')}")
    st.caption("答辩要点：评委可以从输入、关键词、规则、AI、预案、人工确认逐层追溯，避免黑盒决策。")


def render_impact_assessment(result: Dict[str, Any]) -> None:
    is_high = result.get("risk_level") == "高" or result.get("is_emergency") == "是"
    manual_minutes = 8 if is_high else 5
    system_minutes = 2 if is_high else 1
    saved = manual_minutes - system_minutes
    st.markdown("**量化价值估算**")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("传统记录", f"{manual_minutes} 分钟")
    v2.metric("系统辅助", f"{system_minutes} 分钟")
    v3.metric("单次节省", f"{saved} 分钟")
    v4.metric("响应提升", f"{saved / manual_minutes:.0%}")
    st.caption("估算口径：传统客服需要手工记录、判断、派单、通知；系统在转写、分流、工单和预案匹配环节提供辅助。")



def render_real_streaming_section() -> None:
    st.subheader("真实电话流式接入")
    st.info("当前页面的“接收下一段语音”是 audio_chunk 到达的可视化演示；生产环境会由电话平台或 WebRTC 持续推送真实音频帧。")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**1. 电话接入**")
        for item in REALTIME_STREAMING_ARCH["接入方式"]:
            st.write("- " + item)
    with c2:
        st.markdown("**2. 流式识别**")
        for item in REALTIME_STREAMING_ARCH["服务端流程"]:
            st.write("- " + item)
    with c3:
        st.markdown("**3. 工程替换**")
        for item in REALTIME_STREAMING_ARCH["生产替换点"]:
            st.write("- " + item)

    with st.expander("WebSocket 事件契约"):
        st.code(STREAMING_CONTRACT, language="json")

    st.caption("答辩表述：本原型已经按流式事件架构设计，演示按钮只是在无电话平台环境下模拟音频片段到达；接入呼叫中心后无需改变业务链路。")

def risk_banner(level: str, emergency: str):
    if level == "高" or emergency == "是":
        st.markdown(
            '<div class="risk-high">🚨 高风险紧急事件：建议立即启动应急联动</div>',
            unsafe_allow_html=True,
        )
    elif level == "中":
        st.markdown(
            '<div class="risk-mid">⚠️ 中风险事件：建议尽快派单处理</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="risk-low">✅ 一般事件：按常规物业工单流程处理</div>',
            unsafe_allow_html=True,
        )


SLA_MINUTES = {"高": 1, "中": 10, "低": 1440, "待判断": 30}


def parse_dt(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now()


def get_sla_minutes(item: Dict[str, Any]) -> int:
    if item.get("order_type") == "应急事件工单" or item.get("is_emergency") == "是":
        return 1
    return SLA_MINUTES.get(item.get("risk_level", "待判断"), 30)


def enrich_sla(item: Dict[str, Any]) -> Dict[str, Any]:
    created = parse_dt(item.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    minutes = int(item.get("sla_minutes") or get_sla_minutes(item))
    deadline = created.timestamp() + minutes * 60
    remaining = int((deadline - time.time()) // 60)
    done = item.get("status") in ["已完成", "已回访"]
    breached = (remaining < 0) and not done
    return {
        "sla_minutes": minutes,
        "remaining_minutes": remaining,
        "breached": breached,
        "deadline": datetime.fromtimestamp(deadline).strftime("%Y-%m-%d %H:%M:%S"),
        "label": "已超时" if breached else ("已闭环" if done else f"剩余 {max(remaining, 0)} 分钟"),
    }


def run_rule_eval_case(text_value: str, expected_level: str, expected_emergency: str) -> Dict[str, Any]:
    result = analyze_risk(text_value)
    level_ok = result.get("risk_level") == expected_level
    emergency_ok = result.get("is_emergency") == expected_emergency
    return {
        "来电文本": text_value[:34] + ("..." if len(text_value) > 34 else ""),
        "期望风险": expected_level,
        "实际风险": result.get("risk_level"),
        "期望紧急": expected_emergency,
        "实际紧急": result.get("is_emergency"),
        "是否通过": "通过" if level_ok and emergency_ok else "不通过",
        "命中规则": ", ".join(result.get("matched_rules", [])),
    }


# =========================
# 工单池逻辑
# =========================
def calculate_priority_score(text: str, risk_level: str, is_emergency: str) -> int:
    score = 0

    if risk_level == "高" or is_emergency == "是":
        score += 100
    elif risk_level == "中":
        score += 60
    else:
        score += 30

    rule_score = 0
    if isinstance(text, dict):
        rule_score = int(text.get("rule_score", 0))
        text = text.get("content", "")
    score += min(rule_score, 30)

    urgent_words = [
        "漏水", "停电", "电梯", "堵塞", "异味", "门锁",
        "玻璃", "空调", "照明", "水管", "渗水", "积水",
        "下水道", "异响", "晃", "停运"
    ]

    for word in urgent_words:
        if word in text:
            score += 10

    low_words = ["咨询", "建议", "普通投诉", "预约"]
    for word in low_words:
        if word in text:
            score -= 5

    return max(score, 0)


def guess_repair_staff(text: str) -> str:
    for name, info in REPAIR_STAFF.items():
        for skill in info["skills"]:
            if skill in text:
                return name
    return "王师傅"


def add_to_workorder_pool(user_input: str, result: Dict[str, Any]):
    exists = any(
        item["content"] == user_input and item["status"] not in ["已完成", "已回访"]
        for item in st.session_state.workorder_pool
    )

    if exists:
        return False

    score = calculate_priority_score(
        {"content": user_input, "rule_score": result.get("rule_risk", {}).get("score", 0)},
        result["risk_level"],
        result["is_emergency"],
    )

    suggested_staff = guess_repair_staff(user_input)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    order_type = result.get("order_type", "普通维修工单")
    initial_status = result.get("initial_status", "待派单")

    item = {
        "id": f"WO-{len(st.session_state.workorder_pool) + 1:04d}",
        "created_at": now,
        "source": "电话来电",
        "order_type": order_type,
        "content": user_input,
        "risk_level": result["risk_level"],
        "is_emergency": result["is_emergency"],
        "priority_score": score,
        "summary": result["call_summary"],
        "workorder": result["workorder"],
        "status": initial_status,
        "assigned_to": "未派单",
        "assigned_phone": "未派单",
        "suggested_staff": suggested_staff,
        "confirmed_by": "待确认",
        "confirmed_at": "待确认",
        "confirmed_action": "待确认",
        "logs": [f"{now} 创建{order_type}，状态：{initial_status}"],
        "timeline": result.get("timeline", []),
        "rule_risk": result.get("rule_risk", {}),
        "plan": get_matched_plan(result),
        "sla_minutes": get_sla_minutes({"risk_level": result["risk_level"], "is_emergency": result["is_emergency"], "order_type": order_type}),
    }

    st.session_state.workorder_pool.append(item)

    st.session_state.workorder_pool = sorted(
        st.session_state.workorder_pool,
        key=lambda x: x["priority_score"],
        reverse=True,
    )

    persist_runtime_state()
    return True


def route_result_after_analysis(user_input: str, result: Dict[str, Any]) -> str:
    is_high_risk = result.get("risk_level") == "高" or result.get("is_emergency") == "是"

    if is_high_risk:
        result["order_type"] = "应急事件工单"
        result["initial_status"] = "待人工确认"
        ok = add_to_workorder_pool(user_input, result)
        if ok:
            result["route_status"] = "应急事件已自动生成工单，等待客服人工确认联动"
            return "emergency_workorder_created"
        result["route_status"] = "该应急事件已存在未完成工单，等待人工确认"
        return "emergency_duplicate"

    ok = add_to_workorder_pool(user_input, result)
    if ok:
        result["route_status"] = "普通维修事项已自动加入后台工单池"
        return "workorder_created"

    result["route_status"] = "该事项已存在未完成工单，未重复入池"
    return "workorder_duplicate"


def update_workorder_status(order_id: str, new_status: str):
    for item in st.session_state.workorder_pool:
        if item["id"] == order_id:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item["status"] = new_status
            item["logs"].append(f"{now} 状态更新为：{new_status}")
            persist_runtime_state()
            break


def assign_workorder(order_id: str, staff_name: str):
    staff = REPAIR_STAFF[staff_name]

    for item in st.session_state.workorder_pool:
        if item["id"] == order_id:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item["assigned_to"] = f"{staff_name}（{staff['role']}）"
            item["assigned_phone"] = staff["phone"]
            item["status"] = "处理中"
            item["logs"].append(
                f"{now} 已派给：{staff_name}，电话：{staff['phone']}，状态自动进入处理中"
            )
            persist_runtime_state()
            break


# =========================
# 应急外呼模拟
# =========================
def build_emergency_message(result: Dict[str, Any]) -> str:
    return f"""
物业紧急通知：
当前识别到高风险事件。

风险等级：{result.get("risk_level")}
是否紧急：{result.get("is_emergency")}

通话纪要：
{result.get("call_summary")}

风险提示：
{result.get("risk_summary")}

请立即安排人员到现场核查。
"""




def create_phone_demo_record(role: str, phone: str, message: str) -> Dict[str, Any]:
    return {
        "contact": role,
        "phone": phone,
        "message": message,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "模拟手机来电中",
    }


def seed_demo_case(case_name: str) -> None:
    reset_live_call()
    st.session_state.transcript_text = DEMO_CASES[case_name]
    st.session_state.live_call_chunks = [{"time": datetime.now().strftime("%H:%M:%S"), "text": DEMO_CASES[case_name]}]
    st.session_state.call_status = "通话中"
    st.session_state.page = "call"


def clear_demo_state() -> None:
    st.session_state.workorder_pool = []
    st.session_state.call_logs = []
    for key in ["result", "last_input", "phone_demo_record"]:
        st.session_state.pop(key, None)
    save_state("workorder_pool", [])
    save_state("call_logs", [])
    save_state("last_result", None)
    save_state("last_input", "")
    reset_live_call()

def simulate_emergency_call(role: str, phone: str, message: str):
    with st.status(f"正在模拟拨打：{role}（{phone}）", expanded=True) as status:
        time.sleep(0.4)
        st.write("📞 正在呼叫...")
        time.sleep(0.4)
        st.write("✅ 已接通，正在播报应急信息...")
        time.sleep(0.4)
        st.write("📨 通知内容已发送/播报")
        status.update(label=f"已完成模拟外呼：{role}", state="complete")

    return {
        "contact": role,
        "phone": phone,
        "message": message,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "模拟外呼成功",
    }


# =========================
# 初始化状态
# =========================
if "page" not in st.session_state:
    st.session_state.page = "call"

if "call_status" not in st.session_state:
    st.session_state.call_status = "未接入"

if "phone" not in st.session_state:
    st.session_state.phone = ""

if "transcript_text" not in st.session_state:
    st.session_state.transcript_text = ""

if "live_call_chunks" not in st.session_state:
    st.session_state.live_call_chunks = []

if "live_demo_chunks" not in st.session_state:
    st.session_state.live_demo_chunks = []

if "live_demo_index" not in st.session_state:
    st.session_state.live_demo_index = 0

if "live_partial_text" not in st.session_state:
    st.session_state.live_partial_text = ""

if "auto_stream_delay" not in st.session_state:
    st.session_state.auto_stream_delay = 0.7

if "confirm_clear_demo" not in st.session_state:
    st.session_state.confirm_clear_demo = False

if "storage_loaded" not in st.session_state:
    st.session_state.workorder_pool = load_state("workorder_pool", [])
    st.session_state.call_logs = load_state("call_logs", [])
    last_result = load_state("last_result", None)
    last_input = load_state("last_input", "")
    if last_result:
        st.session_state.result = last_result
    if last_input:
        st.session_state.last_input = last_input
    st.session_state.storage_loaded = True

if "workorder_pool" not in st.session_state:
    st.session_state.workorder_pool = []

legacy_status_changed = False
for item in st.session_state.workorder_pool:
    if item.get("status") == "已派单":
        item["status"] = "处理中"
        legacy_status_changed = True
if legacy_status_changed:
    persist_runtime_state()

if "call_logs" not in st.session_state:
    st.session_state.call_logs = []


# =========================
# 侧边栏
# =========================
with st.sidebar:
    st.title("🏢 智联物业 Agent")

    if st.button("客服工作台", use_container_width=True):
        st.session_state.page = "call"
        st.rerun()

    if st.button("演示脚本", use_container_width=True):
        st.session_state.page = "demo_script"
        st.rerun()

    if st.button("模拟手机", use_container_width=True):
        st.session_state.page = "phone_demo"
        st.rerun()

    if st.button("数据看板", use_container_width=True):
        st.session_state.page = "dashboard"
        st.rerun()


    if st.button("真实流式", use_container_width=True):
        st.session_state.page = "streaming"
        st.rerun()

    if st.button("部署与异常", use_container_width=True):
        st.session_state.page = "ops"
        st.rerun()

    if st.button("预案库", use_container_width=True):
        st.session_state.page = "plans"
        st.rerun()

    if st.button("结果展示", use_container_width=True):
        st.session_state.page = "result"
        st.rerun()

    if st.button("后台工单池", use_container_width=True):
        st.session_state.page = "workorders"
        st.rerun()

    if st.button("外呼记录", use_container_width=True):
        st.session_state.page = "call_logs"
        st.rerun()

    if st.button("SLA超时", use_container_width=True):
        st.session_state.page = "sla"
        st.rerun()

    if st.button("规则配置", use_container_width=True):
        st.session_state.page = "rules"
        st.rerun()

    if st.button("评测中心", use_container_width=True):
        st.session_state.page = "eval"
        st.rerun()

    st.divider()
    show_raw = st.toggle("显示原始输出", value=False)
    st.caption("模拟来电 → 语音转写 → 多Agent分析 → 应急外呼 / 工单入池")


# =========================
# 演示脚本
# =========================
if st.session_state.page == "demo_script":
    st.markdown(
        '<div class="title-card"><h1>🎬 赛事演示脚本</h1><p>比赛现场按按钮走，减少误操作，让演示更稳定。</p></div>',
        unsafe_allow_html=True,
    )
    st.subheader("一键准备")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        if st.button("普通维修案例", use_container_width=True):
            seed_demo_case("漏水维修")
            st.rerun()
    with d2:
        if st.button("高风险案例", type="primary", use_container_width=True):
            seed_demo_case("疑似火灾")
            st.rerun()
    with d3:
        if st.button("查看工单池", use_container_width=True):
            st.session_state.page = "workorders"
            st.rerun()
    with d4:
        if st.button("SLA超时", use_container_width=True):
            st.session_state.page = "sla"
            st.rerun()

    st.subheader("推荐演示顺序")
    demo_steps = [
        ("1. 打开客服工作台", "点击高风险案例，展示通话文本和实时风险预警。"),
        ("2. 送入多 Agent 分析", "展示通话纪要、工单、预案、证据链和量化价值。"),
        ("3. 记录人工确认", "说明 AI 不直接报警，高风险必须人工确认。"),
        ("4. 启动模拟外呼", "切到模拟手机页，展示接听效果。"),
        ("5. 打开后台工单池", "展示应急工单状态、日志和闭环。"),
        ("6. 打开 SLA/评测中心", "展示超时机制、规则配置和测试集准确率。"),
    ]
    for title, detail in demo_steps:
        st.markdown(f'<div class="timeline-item"><div class="timeline-title">{title}</div><div>{detail}</div></div>', unsafe_allow_html=True)

    st.subheader("重置演示数据")
    st.warning("该操作会清空本地演示工单、外呼记录和最后一次分析结果，仅用于赛前重置。")
    st.session_state.confirm_clear_demo = st.checkbox("我确认清空本地演示数据", value=st.session_state.confirm_clear_demo)
    if st.button("清空演示数据", use_container_width=True):
        if st.session_state.confirm_clear_demo:
            clear_demo_state()
            st.success("演示数据已清空。")
        else:
            st.error("请先勾选确认。")


# =========================
# 模拟手机
# =========================
elif st.session_state.page == "phone_demo":
    st.markdown(
        '<div class="title-card"><h1>📱 模拟手机接听</h1><p>用于替代真实电话外呼限制，展示手机接到应急通知的效果。</p></div>',
        unsafe_allow_html=True,
    )
    record = st.session_state.get("phone_demo_record")
    if not record:
        st.info("暂无模拟来电。请先在结果页点击“打开手机接听模拟”。")
    else:
        left, right = st.columns([0.9, 1.1])
        with left:
            phone_html = (
                '<div style="max-width:330px;margin:auto;border:10px solid #111827;border-radius:32px;padding:22px;background:#0f172a;color:white;text-align:center;min-height:520px;">'
                '<div style="font-size:14px;color:#94a3b8;">模拟来电</div>'
                f'<div style="font-size:32px;font-weight:800;margin-top:34px;">{record.get("contact", "物业通知")}</div>'
                f'<div style="font-size:18px;color:#cbd5e1;margin-top:12px;">{record.get("phone", "")}</div>'
                '<div style="margin-top:58px;font-size:16px;color:#fef3c7;">高风险事件通知</div>'
                '<div style="margin-top:90px;display:flex;justify-content:space-around;">'
                '<div style="background:#ef4444;border-radius:999px;width:70px;height:70px;line-height:70px;">拒接</div>'
                '<div style="background:#22c55e;border-radius:999px;width:70px;height:70px;line-height:70px;">接听</div>'
                '</div></div>'
            )
            st.markdown(phone_html, unsafe_allow_html=True)
        with right:
            st.subheader("播报内容")
            st.write(record.get("message", ""))
            c1, c2 = st.columns(2)
            with c1:
                if st.button("接听并播报", type="primary", use_container_width=True):
                    record["status"] = "模拟手机已接听"
                    record["answered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.phone_demo_record = record
                    st.session_state.call_logs.append(record)
                    persist_runtime_state()
                    st.success("已模拟接听并播报应急通知。")
            with c2:
                if st.button("未接听转短信", use_container_width=True):
                    record["status"] = "未接听，已转短信兜底"
                    record["answered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.phone_demo_record = record
                    st.session_state.call_logs.append(record)
                    persist_runtime_state()
                    st.warning("已模拟短信兜底通知。")
            st.json(record)


# =========================
# 部署与异常
# =========================
elif st.session_state.page == "ops":
    st.markdown(
        '<div class="title-card"><h1>🧯 部署成本与异常处理</h1><p>把评委最常问的“怎么落地、失败怎么办、花多少钱”提前说清楚。</p></div>',
        unsafe_allow_html=True,
    )
    st.subheader("部署方案")
    st.table([
        {"模块": "小型物业云部署", "配置": "云 ASR + 云大模型 + 云数据库", "适合": "单小区/演示", "成本口径": "按调用量付费"},
        {"模块": "中大型物业私有化", "配置": "本地 ASR/GPU + 私有数据库 + 企业电话平台", "适合": "多小区/集团", "成本口径": "一次部署 + 运维"},
        {"模块": "比赛原型", "配置": "Streamlit + SQLite + CrewAI + Whisper", "适合": "路演验证", "成本口径": "低成本本地运行"},
    ])
    st.subheader("异常情况处理")
    exceptions = [
        ("ASR 听不清", "标记低置信度，提示客服人工复听或要求住户重复关键信息。"),
        ("大模型输出不稳定", "规则引擎兜底，解析失败时展示原文并进入人工复核。"),
        ("外呼失败", "记录失败原因，转短信/企业微信/人工电话兜底。"),
        ("手机号缺失", "生成追问项，要求客服补充联系电话后再闭环。"),
        ("误判高风险", "允许客服主管人工降级，保留降级原因和确认日志。"),
        ("平台未企业认证", "采用模拟外呼，落地时使用物业企业认证账号接入。"),
    ]
    for title, detail in exceptions:
        st.markdown(f'<div class="rule-box"><b>{title}</b><br>{detail}</div>', unsafe_allow_html=True)


# =========================
# 真实流式
# =========================
elif st.session_state.page == "streaming":
    st.markdown(
        '<div class="title-card"><h1>☎️ 真实电话流式接入</h1><p>明确从演示模式到真实电话实时 ASR 的工程落地路径。</p></div>',
        unsafe_allow_html=True,
    )
    render_real_streaming_section()

    st.subheader("生产链路时序")
    flow = [
        ("电话接入", "住户拨入物业热线，呼叫中心建立 stream_id"),
        ("音频切片", "SIP/CTI 或 WebRTC 每 1~3 秒推送 audio_chunk"),
        ("ASR 增量转写", "后端返回 partial_transcript 并追加到通话正文"),
        ("实时预警", "规则引擎同步分析 partial_text，命中高危立即提醒坐席"),
        ("通话结束", "合并全文，调用多 Agent 输出纪要、工单、追问和预案"),
        ("人工确认", "高风险事件生成应急工单，由客服主管确认联动动作"),
    ]
    for title, detail in flow:
        st.markdown(f'<div class="timeline-item"><div class="timeline-title">{title}</div><div>{detail}</div></div>', unsafe_allow_html=True)

    st.subheader("当前原型与真实部署差异")
    st.table([
        {"能力": "音频来源", "当前原型": "按钮模拟分段语音 / 上传录音", "真实部署": "电话平台或 WebRTC 推送真实音频帧"},
        {"能力": "ASR", "当前原型": "faster-whisper 录音后识别 + 分段文本演示", "真实部署": "流式 ASR 服务返回 partial transcript"},
        {"能力": "风险预警", "当前原型": "分段文本实时规则判断", "真实部署": "每段 ASR 结果立即触发规则引擎"},
        {"能力": "业务闭环", "当前原型": "已实现工单、预案、确认、日志", "真实部署": "接入物业工单系统/短信/电话外呼平台"},
    ])


# =========================
# SLA 超时
# =========================
elif st.session_state.page == "sla":
    st.markdown('<div class="title-card"><h1>⏱️ SLA 超时监控</h1><p>按风险等级设置响应时限，超时工单自动标红，方便主管盯办。</p></div>', unsafe_allow_html=True)
    pool = st.session_state.workorder_pool
    timeout_count = sum(1 for x in pool if enrich_sla(x)["breached"])
    waiting_confirm = sum(1 for x in pool if x.get("status") == "待人工确认")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总工单", len(pool))
    c2.metric("超时工单", timeout_count)
    c3.metric("待人工确认", waiting_confirm)
    c4.metric("高风险SLA", "1分钟")
    rows = []
    for item in pool:
        sla = enrich_sla(item)
        rows.append({"工单编号": item.get("id"), "类型": item.get("order_type", "普通维修工单"), "风险": item.get("risk_level"), "状态": item.get("status"), "创建时间": item.get("created_at"), "SLA分钟": sla["sla_minutes"], "截止时间": sla["deadline"], "SLA状态": sla["label"]})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("默认策略：高风险/应急 1 分钟确认，中风险 10 分钟派单，低风险 24 小时回访。")


# =========================
# 规则配置
# =========================
elif st.session_state.page == "rules":
    st.markdown('<div class="title-card"><h1>⚙️ 风险规则配置</h1><p>把关键词、风险等级、应急判断和建议动作从代码里拿出来，便于不同小区调整。</p></div>', unsafe_allow_html=True)
    configs = load_rule_configs()
    edited = []
    for idx, rule in enumerate(configs):
        with st.container(border=True):
            cols = st.columns([1.2, 1, 1, 1])
            with cols[0]:
                name = st.text_input("规则名称", value=str(rule.get("name", "")), key=f"rule_name_{idx}")
            with cols[1]:
                current = str(rule.get("level", "低"))
                level = st.selectbox("风险等级", ["高", "中", "低"], index=["高", "中", "低"].index(current) if current in ["高", "中", "低"] else 2, key=f"rule_level_{idx}")
            with cols[2]:
                emergency = st.checkbox("紧急事件", value=bool(rule.get("emergency", False)), key=f"rule_em_{idx}")
            with cols[3]:
                enabled = st.checkbox("启用", value=bool(rule.get("enabled", True)), key=f"rule_enabled_{idx}")
            keywords = st.text_input("关键词，英文逗号分隔", value=", ".join(rule.get("keywords", [])), key=f"rule_kw_{idx}")
            score = st.slider("规则分", 0, 100, int(rule.get("score", 20)), key=f"rule_score_{idx}")
            action = st.text_area("建议动作", value=str(rule.get("action", "")), height=70, key=f"rule_action_{idx}")
            edited.append({"name": name, "keywords": [x.strip() for x in keywords.split(",") if x.strip()], "level": level, "emergency": emergency, "score": score, "action": action, "enabled": enabled})
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("保存规则配置", type="primary", use_container_width=True):
            save_rule_configs(edited)
            st.success("规则配置已保存，新的来电分析会立即使用。")
            st.rerun()
    with b2:
        if st.button("恢复默认规则", use_container_width=True):
            reset_rule_configs()
            st.warning("已恢复默认规则。")
            st.rerun()
    with b3:
        test_text = st.text_input("快速测试文本", value="楼道有很重烟味")
        if st.button("测试规则", use_container_width=True):
            save_rule_configs(edited)
            st.json(analyze_risk(test_text))


# =========================
# 评测中心
# =========================
elif st.session_state.page == "eval":
    st.markdown('<div class="title-card"><h1>🧪 评测中心</h1><p>用固定测试集检查风险规则的准确率和高风险召回率。</p></div>', unsafe_allow_html=True)
    cases = [("楼道里有很重烟味，好像楼下起火了", "高", "是"), ("闻到燃气味，家里煤气可能泄漏", "高", "是"), ("电梯里有人被困，按警铃没人来", "高", "是"), ("老人摔倒流血，需要帮忙", "高", "是"), ("厨房水管一直漏水，地面有积水", "中", "否"), ("2号楼电梯运行时异响而且有点晃", "中", "否"), ("家里停电，可能是跳闸", "中", "否"), ("楼下晚上聊天太吵，影响休息", "低", "否"), ("想咨询物业费缴纳时间", "低", "否"), ("下水道堵塞，有返味", "中", "否")]
    rows = [run_rule_eval_case(text_value, level, emergency) for text_value, level, emergency in cases]
    passed = sum(1 for x in rows if x["是否通过"] == "通过")
    high_cases = [x for x in rows if x["期望风险"] == "高"]
    high_recalled = sum(1 for x in high_cases if x["实际风险"] == "高")
    c1, c2, c3 = st.columns(3)
    c1.metric("测试样本", len(rows))
    c2.metric("规则准确率", f"{passed / len(rows):.0%}")
    c3.metric("高风险召回率", f"{high_recalled / len(high_cases):.0%}" if high_cases else "0%")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption("评测中心用于证明规则引擎不是拍脑袋写的；后续可导入真实历史来电形成标准测试集。")


# =========================
# 预案库
# =========================
elif st.session_state.page == "plans":
    st.markdown(
        '<div class="title-card"><h1>📚 标准处置预案库</h1><p>把 AI 输出落到可执行 SOP，客服按预案确认、派单和回访。</p></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for idx, plan in enumerate(INCIDENT_PLANS.values()):
        with cols[idx % 2]:
            render_plan_card(plan)


# =========================
# 数据看板
# =========================
elif st.session_state.page == "dashboard":
    st.markdown(
        '<div class="title-card"><h1>📈 物业事件数据看板</h1><p>面向比赛演示的运营态势页：展示接入、分流、派单、外呼和闭环效果。</p></div>',
        unsafe_allow_html=True,
    )

    pool = st.session_state.workorder_pool
    logs = st.session_state.call_logs
    high_count = sum(1 for x in pool if x.get("risk_level") == "高" or x.get("is_emergency") == "是")
    done_count = sum(1 for x in pool if x.get("status") in ["已完成", "已回访"])
    pending_count = sum(1 for x in pool if x.get("status") in ["待人工确认", "应急联动确认", "待派单", "处理中"])
    close_rate = f"{(done_count / len(pool) * 100):.0f}%" if pool else "0%"

    confirm_count = sum(1 for x in pool if x.get("status") == "待人工确认")
    timeout_count = sum(1 for x in pool if enrich_sla(x)["breached"])
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("累计工单", len(pool))
    k2.metric("高风险", high_count)
    k3.metric("待确认", confirm_count)
    k4.metric("超时", timeout_count)
    k5.metric("闭环率", close_rate)
    k6.metric("外呼记录", len(logs))

    total_saved = sum(6 if x.get("risk_level") == "高" or x.get("is_emergency") == "是" else 4 for x in pool)
    e1, e2, e3 = st.columns(3)
    e1.metric("预计节省客服时间", f"{total_saved} 分钟")
    e2.metric("平均自动分流时长", "< 2 分钟")
    e3.metric("高风险可追溯率", "100%" if high_count else "0%")

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("风险与状态分布")
        risk_rows = []
        for level in ["高", "中", "低", "待判断"]:
            risk_rows.append({"风险等级": level, "数量": sum(1 for x in pool if x.get("risk_level") == level)})
        st.bar_chart(risk_rows, x="风险等级", y="数量")

        status_rows = []
        for status in ["待人工确认", "应急联动确认", "待派单", "处理中", "已完成", "已回访"]:
            status_rows.append({"工单状态": status, "数量": sum(1 for x in pool if x.get("status") == status)})
        st.bar_chart(status_rows, x="工单状态", y="数量")

    with right:
        st.subheader("最新事件")
        latest = sorted(pool, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
        if not latest:
            st.info("暂无事件。可以先用演示案例完成一次普通维修分析，系统会自动生成工单。")
        for item in latest:
            with st.container(border=True):
                st.markdown(f"**{item.get('id')}｜{item.get('risk_level')}风险｜{item.get('status')}**")
                st.write(item.get("content", "")[:90])
                st.caption(f"建议人员：{item.get('suggested_staff', '待确认')}｜优先级：{item.get('priority_score', 0)}")

    st.subheader("比赛展示话术")
    st.info("本系统采用规则引擎兜底 + 多 Agent 语义分析 + 人工确认执行，避免纯 AI 自动处置带来的安全风险，同时保留完整工单和外呼审计记录。")


# =========================
# 首页
# =========================
elif st.session_state.page == "home":
    st.markdown(
        """
        <div class="title-card">
            <h1>🏢 智联物业 Agent：来电智处助手</h1>
            <p>面向物业/社区场景，实现来电接入、语音转写、风险识别、工单生成、应急联动和后台派单闭环。</p>
            <span class="tag">模拟来电</span>
            <span class="tag">真实语音转文本</span>
            <span class="tag">多Agent协同</span>
            <span class="tag">风险优先</span>
            <span class="tag">后台派单</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("接入方式", "模拟电话")
    c2.metric("语音识别", "Whisper")
    c3.metric("处置模式", "多Agent")
    c4.metric("后台工单", len(st.session_state.workorder_pool))

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("系统流程")
    st.write(
        "📞 模拟来电 → 🎙️ 录音/上传 → 📝 语音转文本 → 🤖 多Agent分析 → 🚨 高风险外呼 / 🧾 普通维修入池 → 👷 派单维修 → ✅ 回访闭环"
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("比赛演示模式")
    cols = st.columns(4)

    for i, (name, text) in enumerate(DEMO_CASES.items()):
        with cols[i]:
            if st.button(name, use_container_width=True):
                reset_live_call()
                st.session_state.transcript_text = text
                st.session_state.live_call_chunks = [{"time": datetime.now().strftime("%H:%M:%S"), "text": text}]
                st.session_state.page = "call"
                st.session_state.call_status = "通话中"
                st.rerun()

    if st.button("🚀 开始模拟来电", type="primary", use_container_width=True):
        st.session_state.page = "call"
        st.session_state.call_status = "未接入"
        st.rerun()


# =========================
# 模拟来电页
# =========================
elif st.session_state.page == "call":
    st.markdown(
        '<div class="title-card"><h1>📞 客服实时处置工作台</h1><p>一屏完成来电接入、同步转写、实时预警、人工确认和工单闭环。</p></div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1])

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("① 来电状态")

        if st.session_state.call_status == "未接入":
            st.info("当前无来电")
            if st.button("📞 模拟来电", type="primary", use_container_width=True):
                st.session_state.phone = random.choice(
                    ["138****5678", "186****2391", "139****8806"]
                )
                reset_live_call()
                st.session_state.call_status = "来电中"
                st.rerun()

        elif st.session_state.call_status == "来电中":
            st.warning(f"📞 来电中：{st.session_state.phone}")
            if st.button("✅ 接听并开始录音", type="primary", use_container_width=True):
                st.session_state.call_status = "通话中"
                st.rerun()

        elif st.session_state.call_status == "通话中":
            st.success(f"通话中：{st.session_state.phone or '模拟号码'}")
            st.write("实时识别状态：可逐段接收语音文本，并同步进行风险预警")

        elif st.session_state.call_status == "录音完成":
            st.success(f"录音完成：{st.session_state.phone}")

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("② 实时通话识别")

        if st.session_state.call_status not in ["通话中", "录音完成"]:
            st.info("请先模拟来电并接听，再开始实时识别。")
        else:
            live_demo_name = st.selectbox("实时演示话术", list(DEMO_CASES.keys()), key="live_demo_name")
            d1, d2 = st.columns(2)

            with d1:
                if st.button("接收下一段语音", use_container_width=True):
                    if not st.session_state.live_demo_chunks or st.session_state.get("live_demo_source") != live_demo_name:
                        st.session_state.live_demo_chunks = split_live_demo(DEMO_CASES[live_demo_name])
                        st.session_state.live_demo_index = 0
                        st.session_state.live_demo_source = live_demo_name

                    if st.session_state.live_demo_index < len(st.session_state.live_demo_chunks):
                        append_live_chunk(st.session_state.live_demo_chunks[st.session_state.live_demo_index])
                        st.session_state.live_demo_index += 1
                        st.rerun()
                    else:
                        st.info("当前演示话术已全部识别完成。")

            with d2:
                if st.button("接收整通演示", use_container_width=True):
                    reset_live_call()
                    for part in split_live_demo(DEMO_CASES[live_demo_name]):
                        append_live_chunk(part)
                    st.session_state.live_demo_source = live_demo_name
                    st.session_state.live_demo_index = len(st.session_state.live_call_chunks)
                    st.rerun()

            st.session_state.auto_stream_delay = st.slider("自动流式间隔（秒）", 0.2, 1.5, float(st.session_state.auto_stream_delay), 0.1)
            if st.button("自动流式播放", type="primary", use_container_width=True):
                reset_live_call()
                st.session_state.live_demo_source = live_demo_name
                chunks = split_live_demo(DEMO_CASES[live_demo_name])
                progress = st.progress(0)
                live_box = st.empty()
                for idx, part in enumerate(chunks, 1):
                    append_live_chunk(part)
                    rule = analyze_risk(st.session_state.transcript_text)
                    live_box.info(f"第 {idx}/{len(chunks)} 段：{part}｜实时风险：{rule['risk_level']}｜紧急：{rule['is_emergency']}")
                    progress.progress(idx / len(chunks))
                    time.sleep(float(st.session_state.auto_stream_delay))
                st.session_state.live_demo_index = len(chunks)
                st.success("自动流式播放完成，右侧文本已同步生成。")
                st.rerun()

            manual_chunk = st.text_area(
                "人工实时听写 / ASR 分段结果",
                key="live_partial_text",
                height=90,
                placeholder="例如：厨房水管一直漏水，地面已经有积水",
            )

            a1, a2 = st.columns(2)
            with a1:
                if st.button("追加到实时转写", type="primary", use_container_width=True):
                    append_live_chunk(manual_chunk)
                    st.rerun()
            with a2:
                if st.button("清空实时记录", use_container_width=True):
                    reset_live_call()
                    st.rerun()

            render_live_transcript()
            render_live_risk_preview(st.session_state.transcript_text)
            with st.expander("真实电话流式说明"):
                render_real_streaming_section()

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("③ 录音/上传后识别")

        audio_record = st.audio_input("浏览器录音模拟电话")
        audio_upload = st.file_uploader(
            "或上传电话录音",
            type=["wav", "mp3", "m4a"],
        )

        audio_file = audio_record or audio_upload

        if audio_file is not None:
            st.audio(audio_file)
            st.session_state.audio_file = audio_file
            st.session_state.call_status = "录音完成"

        if st.button("📝 开始真实语音转文本", use_container_width=True):
            if "audio_file" not in st.session_state:
                st.warning("请先录音或上传一段音频。")
            else:
                with st.spinner("正在加载 Whisper 模型并识别语音，首次运行可能稍慢..."):
                    text = real_asr(st.session_state.audio_file)
                    st.session_state.transcript_text = text
                    st.success("语音转写完成")
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("④ 一键填入完整文本")

        demo_name = st.selectbox("选择演示案例", list(DEMO_CASES.keys()))

        if st.button("填入演示文本", use_container_width=True):
            reset_live_call()
            st.session_state.transcript_text = DEMO_CASES[demo_name]
            st.session_state.live_call_chunks = [{"time": datetime.now().strftime("%H:%M:%S"), "text": DEMO_CASES[demo_name]}]
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("⑤ 实时转写文本确认")

        transcript = st.text_area(
            "语音转写结果，可人工修正",
            key="transcript_text",
            height=260,
            placeholder="这里显示语音转写后的物业来电文本，也可以直接手动输入测试文本。",
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("🤖 送入多Agent分析", type="primary", use_container_width=True):
                if not transcript.strip():
                    st.warning("请先输入或生成转写文本。")
                else:
                    with st.spinner("正在进行风险研判、工单生成和闭环整合..."):
                        text_input = transcript.strip()
                        rule_risk = analyze_risk(text_input)
                        raw = call_crew(text_input)
                        parsed = parse_result(raw)
                        merged = merge_ai_and_rule_risk(parsed["risk_level"], parsed["is_emergency"], rule_risk)
                        parsed["ai_risk_level"] = parsed["risk_level"]
                        parsed["ai_is_emergency"] = parsed["is_emergency"]
                        parsed["risk_level"] = merged["risk_level"]
                        parsed["is_emergency"] = merged["is_emergency"]
                        parsed["risk_source"] = merged["source"]
                        parsed["rule_risk"] = rule_risk
                        parsed["analysis_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        parsed["timeline"] = build_event_timeline(text_input, parsed)
                        route_result_after_analysis(text_input, parsed)
                        st.session_state.result = parsed
                        st.session_state.last_input = text_input
                        persist_runtime_state()
                        st.session_state.page = "result"
                        st.rerun()

        with c2:
            if st.button("🧹 重置来电", use_container_width=True):
                for k in ["audio_file", "result", "last_input"]:
                    st.session_state.pop(k, None)

                reset_live_call()
                st.session_state.call_status = "未接入"
                st.session_state.phone = ""

                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("演示说明")
        st.write(
            "通话中可同步形成转写文本并实时预警；确认后再送入多 Agent 生成工单和闭环处置结果。"
        )
        st.markdown("</div>", unsafe_allow_html=True)


# =========================
# 结果展示页
# =========================
elif st.session_state.page == "result":
    st.markdown(
        '<div class="title-card"><h1>📊 智能闭环处置结果</h1><p>系统已完成通话纪要、风险研判、工单待办、建议追问和风险分流。</p></div>',
        unsafe_allow_html=True,
    )

    if "result" not in st.session_state:
        st.warning("暂无分析结果，请先完成模拟来电分析。")
        if st.button("返回模拟来电"):
            st.session_state.page = "call"
            st.rerun()

    else:
        result = st.session_state.result
        is_high_risk = result["risk_level"] == "高" or result["is_emergency"] == "是"

        risk_banner(result["risk_level"], result["is_emergency"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("风险等级", result["risk_level"])
        m2.metric("是否紧急", result["is_emergency"])
        m3.metric("来电号码", st.session_state.get("phone", "待确认") or "待确认")
        m4.metric("分流结果", "应急外呼" if is_high_risk else "后台工单池")

        st.caption(f"判断来源：{result.get('risk_source', 'AI分析')}｜AI原始判断：{result.get('ai_risk_level', result['risk_level'])}/{result.get('ai_is_emergency', result['is_emergency'])}")
        if result.get("route_status"):
            st.success(result["route_status"])

        c1, c2 = st.columns(2)

        with c1:
            with st.container(border=True):
                st.subheader("📞 通话纪要")
                st.markdown(result["call_summary"])

            with st.container(border=True):
                st.subheader("🛠️ 工单待办")
                st.markdown(result["workorder"])

        with c2:
            with st.container(border=True):
                st.subheader("⚠️ 风险提示")
                st.markdown(result["risk_summary"])

            with st.container(border=True):
                st.subheader("❓ 建议追问")
                st.markdown(result["questions"])

        with st.container(border=True):
            st.subheader("🧭 事件处置时间线")
            render_timeline(result.get("timeline", []))

        with st.container(border=True):
            st.subheader("🧩 风险规则解释")
            render_rule_explain(result)

        with st.container(border=True):
            st.subheader("📚 匹配处置预案")
            render_plan_card(get_matched_plan(result))

        with st.container(border=True):
            st.subheader("🔎 决策证据链")
            render_evidence_chain(result)

        with st.container(border=True):
            st.subheader("📐 量化价值评估")
            render_impact_assessment(result)

        if is_high_risk:
            with st.container(border=True):
                st.subheader("🚨 应急联动建议")
                st.markdown(result["emergency_block"])

            st.subheader("👤 人工确认")
            h1, h2 = st.columns(2)
            with h1:
                confirmed_by = st.selectbox("确认人", ["客服主管", "物业值班经理", "安保主管"], key="confirm_by")
            with h2:
                confirm_action = st.selectbox("确认动作", ["启动应急联动", "先派人现场核查", "降级为普通工单"], key="confirm_action")
            if st.button("记录人工确认", type="primary", use_container_width=True):
                if confirm_emergency_action(st.session_state.get("last_input", ""), confirmed_by, confirm_action):
                    st.success("已记录人工确认，相关应急工单已更新。")
                else:
                    st.warning("未找到对应的待确认应急工单，请检查是否已重复处理。")

            st.subheader("📞 紧急外呼")

            message = build_emergency_message(result)

            call_mode = st.radio(
                "外呼模式",
                ["页面模拟外呼", "腾讯云真实外呼"],
                horizontal=True,
            )

            if call_mode == "页面模拟外呼":
                selected_contacts = st.multiselect(
                    "选择需要通知的人员",
                    list(EMERGENCY_CONTACTS.keys()),
                    default=["物业值班室", "安保主管"],
                )

                ccall1, ccall2 = st.columns(2)
                with ccall1:
                    if st.button("🚨 启动页面模拟外呼", type="primary", use_container_width=True):
                        for role in selected_contacts:
                            phone = EMERGENCY_CONTACTS[role]
                            record = simulate_emergency_call(role, phone, message)
                            st.session_state.call_logs.append(record)
                            st.json(record)

                        persist_runtime_state()
                        st.success("紧急联系人已完成模拟通知。")
                with ccall2:
                    if st.button("📱 打开手机接听模拟", use_container_width=True):
                        role = selected_contacts[0] if selected_contacts else "物业值班室"
                        phone = EMERGENCY_CONTACTS.get(role, "13800001111")
                        st.session_state.phone_demo_record = create_phone_demo_record(role, phone, message)
                        st.session_state.page = "phone_demo"
                        st.rerun()

            else:
                status = credentials_status()
                st.info(f"腾讯云密钥状态：SecretId {status['secret_id']}｜SecretKey {status['secret_key']}")
                st.warning("真实外呼会把测试手机号发送到腾讯云语音消息服务，并可能产生费用。请只填写你本人或已授权的测试号码。")

                tc1, tc2 = st.columns(2)
                with tc1:
                    test_phone = st.text_input("测试手机号", placeholder="例如：13800138000", key="tencent_test_phone")
                    voice_sdk_appid = st.text_input("VoiceSdkAppid", placeholder="腾讯云语音消息应用 ID", key="tencent_voice_sdk_appid")
                with tc2:
                    template_id = st.text_input("TemplateId", placeholder="审核通过的语音模板 ID", key="tencent_template_id")
                    template_params = st.text_input("模板参数", placeholder="多个参数用英文逗号分隔，可留空", key="tencent_template_params")

                with st.expander("建议语音模板内容"):
                    st.write("物业紧急通知：当前识别到高风险事件，请立即查看系统工单并安排人员到现场核查。")
                    st.caption("腾讯云语音通知通常需要先在控制台提交模板并审核，通过后才能通过 TemplateId 调用。")

                confirm_real_call = st.checkbox(
                    "我确认该手机号已授权用于测试，并同意调用腾讯云发起真实语音外呼",
                    key="confirm_tencent_real_call",
                )

                if st.button("☎️ 调用腾讯云真实外呼", type="primary", use_container_width=True):
                    if not confirm_real_call:
                        st.error("请先勾选确认授权。")
                    elif not test_phone.strip() or not voice_sdk_appid.strip() or not template_id.strip():
                        st.error("请填写测试手机号、VoiceSdkAppid 和 TemplateId。")
                    else:
                        params = [p.strip() for p in template_params.split(",") if p.strip()]
                        with st.spinner("正在调用腾讯云语音消息接口..."):
                            response = send_tts_voice(
                                called_number=test_phone.strip(),
                                voice_sdk_appid=voice_sdk_appid.strip(),
                                template_id=template_id.strip(),
                                template_params=params,
                                play_times=2,
                                session_context=f"property-agent-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            )

                        record = {
                            "contact": "腾讯云测试号码",
                            "phone": test_phone.strip()[:3] + "****" + test_phone.strip()[-4:],
                            "message": "腾讯云语音通知模板外呼",
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "腾讯云接口已调用",
                            "response": response,
                        }
                        st.session_state.call_logs.append(record)
                        persist_runtime_state()
                        st.json(response)
                        if response.get("Response", {}).get("Error"):
                            st.error("腾讯云返回错误，请检查模板、AppID、资质或号码格式。")
                        else:
                            st.success("腾讯云真实外呼请求已提交，请留意手机来电。")

        else:
            st.subheader("🧾 普通维修工单入池")
            st.info("该事项未触发应急外呼，分析完成后已自动进入后台工单池，由物业统一安排维修人员处理。")

            if st.button("重新检查工单入池状态", type="primary", use_container_width=True):
                ok = add_to_workorder_pool(st.session_state.get("last_input", ""), result)

                if ok:
                    st.success("已补加入后台工单池，并完成优先级排序。")
                else:
                    st.warning("该事项已存在未完成工单，未重复加入。")

        if show_raw:
            with st.expander("查看原始 CrewAI 输出"):
                st.code(result["raw_text"])

        st.divider()

        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("📞 再模拟一通电话", use_container_width=True):
                st.session_state.page = "call"
                st.session_state.call_status = "未接入"
                st.rerun()

        with c2:
            if st.button("🧾 查看后台工单池", use_container_width=True):
                st.session_state.page = "workorders"
                st.rerun()

        with c3:
            if st.button("📞 返回客服工作台", use_container_width=True):
                st.session_state.page = "call"
                st.rerun()


# =========================
# 后台工单池：紧凑表格版
# =========================
elif st.session_state.page == "workorders":
    st.markdown(
        '<div class="title-card"><h1>🧾 后台工单池</h1><p>普通维修、投诉建议和应急事件统一入池，支持排序、派单、确认和闭环。</p></div>',
        unsafe_allow_html=True,
    )

    pool = st.session_state.workorder_pool

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总工单", len(pool))
    c2.metric("待派单", sum(1 for x in pool if x["status"] == "待派单"))
    c3.metric("处理中", sum(1 for x in pool if x["status"] == "处理中"))
    c4.metric("已完成", sum(1 for x in pool if x["status"] in ["已完成", "已回访"]))

    if not pool:
        st.info("暂无待处理工单。")

    else:
        st.subheader("筛选条件")

        f1, f2, f3 = st.columns(3)

        with f1:
            status_filter = st.selectbox(
                "状态",
                ["全部", "待人工确认", "应急联动确认", "待派单", "处理中", "已完成", "已回访"]
            )

        with f2:
            risk_filter = st.selectbox(
                "风险等级",
                ["全部", "高", "中", "低", "待判断"]
            )

        with f3:
            keyword = st.text_input(
                "关键词搜索",
                placeholder="如：漏水、电梯、门锁"
            )

        filtered = pool

        if status_filter != "全部":
            filtered = [x for x in filtered if x["status"] == status_filter]

        if risk_filter != "全部":
            filtered = [x for x in filtered if x["risk_level"] == risk_filter]

        if keyword.strip():
            kw = keyword.strip()
            filtered = [
                x for x in filtered
                if kw in x["content"] or kw in x["workorder"] or kw in x["assigned_to"]
            ]

        filtered = sorted(
            filtered,
            key=lambda x: x["priority_score"],
            reverse=True,
        )

        st.subheader("工单列表")

        table_data = []

        for item in filtered:
            content_short = item["content"]
            if len(content_short) > 35:
                content_short = content_short[:35] + "..."

            sla = enrich_sla(item)
            table_data.append(
                {
                    "工单编号": item["id"],
                    "状态": item["status"],
                    "SLA": sla["label"],
                    "类型": item.get("order_type", "普通维修工单"),
                    "风险": item["risk_level"],
                    "优先级": item["priority_score"],
                    "建议人员": item["suggested_staff"],
                    "负责人": item["assigned_to"],
                    "来电摘要": content_short,
                    "创建时间": item["created_at"],
                }
            )

        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("工单详情与操作")

        order_ids = [x["id"] for x in filtered]

        if not order_ids:
            st.info("当前筛选条件下暂无工单。")

        else:
            selected_id = st.selectbox("选择工单编号查看详情", order_ids)

            selected_order = next(
                x for x in st.session_state.workorder_pool
                if x["id"] == selected_id
            )

            left, right = st.columns([1.3, 1])

            with left:
                with st.container(border=True):
                    st.markdown(f"### {selected_order['id']} 工单详情")

                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("状态", selected_order["status"])
                    d2.metric("类型", selected_order.get("order_type", "普通维修工单"))
                    d3.metric("风险等级", selected_order["risk_level"])
                    d4.metric("优先级", selected_order["priority_score"])

                    st.write(f"**创建时间：** {selected_order['created_at']}")
                    st.write(f"**建议责任人：** {selected_order['suggested_staff']}")
                    st.write(f"**当前负责人：** {selected_order['assigned_to']}")
                    st.write(f"**联系电话：** {selected_order['assigned_phone']}")
                    if selected_order.get("order_type") == "应急事件工单":
                        st.write(f"**人工确认：** {selected_order.get('confirmed_by', '待确认')}｜{selected_order.get('confirmed_action', '待确认')}｜{selected_order.get('confirmed_at', '待确认')}")

                    st.markdown("**来电内容：**")
                    st.write(selected_order["content"])

                    st.markdown("**工单待办：**")
                    st.markdown(selected_order["workorder"])

                    if selected_order.get("timeline"):
                        st.markdown("**处置时间线：**")
                        render_timeline(selected_order.get("timeline", []))

                    if selected_order.get("rule_risk"):
                        st.markdown("**规则命中：**")
                        st.write(", ".join(selected_order.get("rule_risk", {}).get("matched_rules", [])))

                    if selected_order.get("plan"):
                        st.markdown("**匹配预案：**")
                        render_plan_card(selected_order.get("plan"))

            with right:
                with st.container(border=True):
                    st.markdown("### 派单/处置操作")

                    current_status = selected_order.get("status", "待派单")
                    can_dispatch = current_status in ["待派单", "应急联动确认"]

                    if current_status == "待人工确认":
                        st.warning("该应急工单仍待人工确认联动，确认后再派单处置。")

                    elif can_dispatch:
                        staff_list = list(REPAIR_STAFF.keys())
                        default_staff = selected_order["suggested_staff"]

                        staff_name = st.selectbox(
                            "选择维修人员",
                            staff_list,
                            index=staff_list.index(default_staff)
                            if default_staff in staff_list else 0,
                            key=f"detail_staff_{selected_order['id']}",
                        )

                        staff_info = REPAIR_STAFF[staff_name]
                        st.info(
                            f"人员类型：{staff_info['role']}｜电话：{staff_info['phone']}"
                        )

                        if st.button("派单并进入处理中", type="primary", use_container_width=True):
                            assign_workorder(selected_order["id"], staff_name)
                            st.success(f"{selected_order['id']} 已派给 {staff_name}，状态已自动进入处理中")
                            st.rerun()

                    elif current_status == "处理中":
                        st.success("该工单已进入处理中，等待维修人员完成处置。")
                        if st.button("标记完成", type="primary", use_container_width=True):
                            update_workorder_status(selected_order["id"], "已完成")
                            st.rerun()

                    elif current_status == "已完成":
                        st.info("维修已完成，下一步进行回访归档。")
                        if st.button("完成回访", type="primary", use_container_width=True):
                            update_workorder_status(selected_order["id"], "已回访")
                            st.rerun()

                    elif current_status == "已回访":
                        st.success("该工单已完成回访并归档。")

                    else:
                        st.info("当前状态无需派单操作，可按实际处置结果更新。")

                with st.container(border=True):
                    st.markdown("### 处置日志")

                    for log in selected_order["logs"]:
                        st.write("• " + log)


# =========================
# 外呼记录页
# =========================
elif st.session_state.page == "call_logs":
    st.markdown(
        '<div class="title-card"><h1>📞 应急外呼记录</h1><p>记录高风险事件触发后的模拟外呼过程。</p></div>',
        unsafe_allow_html=True,
    )

    logs = st.session_state.call_logs

    if not logs:
        st.info("暂无外呼记录。")

    else:
        for log in logs[::-1]:
            with st.container(border=True):
                c1, c2, c3 = st.columns(3)
                c1.metric("联系人", log["contact"])
                c2.metric("电话", log["phone"])
                c3.metric("状态", log["status"])

                st.write(f"时间：{log['time']}")

                with st.expander("查看外呼内容"):
                    st.write(log["message"])


# 运行命令：
# uv run python -m streamlit run app.py


