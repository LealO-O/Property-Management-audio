# 智联物业 Agent：物业来电智能助手

面向物业来电场景的风险识别与工单闭环处置系统。系统支持来电演示、录音识别、规则风险判断、多 Agent 分析、后台工单池、SLA 超时监控、规则配置与评测中心。

## 核心能力

- 物业来电文本/录音识别
- faster-whisper 语音转文字
- 规则引擎安全兜底
- CrewAI 多 Agent 风险研判与工单生成
- 高风险人工确认
- 工单派单、处理中、完成、回访闭环
- SLA 超时监控
- 规则配置页
- 评测中心

## 本地运行

建议 Python 版本：3.10 - 3.13。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

打开浏览器访问：

```text
http://localhost:8501
```

## 环境变量

复制 `.env.example` 为 `.env`，填入自己的 Key。不要提交 `.env`。

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek/deepseek-chat
SERPER_API_KEY=
TENCENTCLOUD_SECRET_ID=
TENCENTCLOUD_SECRET_KEY=
TENCENT_VMS_REGION=ap-guangzhou
```

## Streamlit Community Cloud 部署

1. 将本仓库上传到 GitHub。
2. 打开 Streamlit Community Cloud。
3. New app 选择本仓库。
4. Main file path 填写：`app.py`。
5. 在 Secrets 中填入需要的密钥，例如：

```toml
DEEPSEEK_API_KEY = "你的Key"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek/deepseek-chat"
SERPER_API_KEY = "你的Key"
TENCENTCLOUD_SECRET_ID = "你的SecretId"
TENCENTCLOUD_SECRET_KEY = "你的SecretKey"
TENCENT_VMS_REGION = "ap-guangzhou"
```

## 电话平台接入说明

当前版本已完成来电演示、录音识别、流式识别、风险研判与工单闭环链路。生产部署时可接入物业电话平台、呼叫中心或 WebRTC，将通话音频流推送给系统。

## 安全说明

本仓库不应包含 `.env`、`.venv`、`.idea`、本地数据库和真实密钥。
