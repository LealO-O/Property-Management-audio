import os
from typing import List

from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from present.tools.call_tool import emergency_call_tool, suggest_emergency_phone_tool

os.environ.setdefault("CREWAI_TRACING", "false")


def get_llm():
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    kwargs = {"model": model, "base_url": base_url}
    if api_key:
        kwargs["api_key"] = api_key
    return LLM(**kwargs)


@CrewBase
class Present:
    """物业来电闭环智能助手"""

    @agent
    def transcript_agent(self) -> Agent:
        return Agent(
            role="通话纪要专员",
            goal="将用户输入的电话内容整理成清晰、客观、简洁的物业通话纪要",
            backstory="你擅长从居民来电中提取事件、地点、联系人、诉求、现场状态等关键信息。",
            llm=get_llm(),
            verbose=True,
            allow_delegation=False,
        )

    @agent
    def risk_agent(self) -> Agent:
        return Agent(
            role="风险研判专员",
            goal="优先识别紧急风险，判断是否需要立即联动外部应急资源",
            backstory="你在物业场景中优先识别火灾、燃气泄漏、电梯困人、人员受伤、治安异常等高风险事件。",
            llm=get_llm(),
            verbose=True,
            allow_delegation=False,
            tools=[suggest_emergency_phone_tool, emergency_call_tool],
        )

    @agent
    def task_agent(self) -> Agent:
        return Agent(
            role="工单任务专员",
            goal="把来电内容整理成物业可执行的待办事项和闭环动作",
            backstory="你擅长生成责任清晰、优先级明确的物业工单。",
            llm=get_llm(),
            verbose=True,
            allow_delegation=False,
        )

    @agent
    def clarify_agent(self) -> Agent:
        return Agent(
            role="追问补全专员",
            goal="找出信息缺口并生成必要追问",
            backstory="你擅长识别处置中缺失的关键信息，并提出最必要的追问问题。",
            llm=get_llm(),
            verbose=True,
            allow_delegation=False,
        )

    @agent
    def summary_agent(self) -> Agent:
        return Agent(
            role="闭环输出专员",
            goal="将前面各模块结果整合成统一的物业事件闭环输出",
            backstory="你负责把纪要、风险、待办、追问等内容整合成专业清晰的最终结果。",
            llm=get_llm(),
            verbose=True,
            allow_delegation=False,
        )

    @task
    def risk_assessment_task(self) -> Task:
        return Task(
            description=(
                "请基于以下真实物业来电内容做风险评估，不要虚构住址、电话、联系人、现场细节：\n\n"
                "{input}\n\n"
                "要求：\n"
                "1. 判断是否属于紧急事件。\n"
                "2. 给出风险等级：高 / 中 / 低。\n"
                "3. 说明风险原因。\n"
                "4. 给出建议动作。\n"
                "5. 如果属于紧急事件，可调用工具输出建议联系电话和紧急外呼话术。\n"
                "6. 若原始输入中没有具体地址、电话、人名，不得自行编造，只能标注“待确认”。"
            ),
            expected_output=(
                "结构化风险研判结果，包括：是否紧急、风险等级、风险原因、建议动作、"
                "建议联系电话、紧急外呼话术（如适用）。"
            ),
            agent=self.risk_agent(),
        )

    @task
    def transcript_task(self) -> Task:
        return Task(
            description=(
                "请基于以下真实物业来电内容生成通话纪要，不要补造不存在的信息：\n\n"
                "{input}\n\n"
                "要求提取：\n"
                "- 来电人身份（如能判断）\n"
                "- 事件概述\n"
                "- 事发地点\n"
                "- 联系方式（如有）\n"
                "- 当前诉求\n"
                "- 现场状态\n"
                "若原文未提及，明确写“未提供”或“待确认”。"
            ),
            expected_output="规范的物业通话纪要。",
            agent=self.transcript_agent(),
        )

    @task
    def workorder_task(self) -> Task:
        return Task(
            description=(
                "请基于以下真实物业来电内容生成物业工单待办，不要编造不存在的细节：\n\n"
                "{input}\n\n"
                "要求输出：\n"
                "- 工单标题\n"
                "- 工单类型\n"
                "- 优先级\n"
                "- 责任部门\n"
                "- 处理建议\n"
                "- 是否需要回访\n"
                "- 闭环标准"
            ),
            expected_output="结构化物业工单待办。",
            agent=self.task_agent(),
        )

    @task
    def clarify_task(self) -> Task:
        return Task(
            description=(
                "请基于以下真实物业来电内容识别信息缺口，生成3~5条必要追问：\n\n"
                "{input}\n\n"
                "优先追问：\n"
                "- 地址是否完整\n"
                "- 是否有人受伤/被困\n"
                "- 事件是否仍在持续\n"
                "- 联系人电话\n"
                "- 是否已联系相关部门\n"
                "不要输出无关追问。"
            ),
            expected_output="3~5条必要追问。",
            agent=self.clarify_agent(),
        )

    @task
    def final_summary_task(self) -> Task:
        return Task(
            description=(
                "请整合前面任务结果，输出最终物业来电闭环处置结果。\n"
                "必须包含：\n"
                "1. 通话纪要\n"
                "2. 风险提示\n"
                "3. 工单待办\n"
                "4. 建议追问\n"
                "5. 如属紧急事件，单独输出“应急联动建议”\n\n"
                "禁止编造输入中不存在的住址、电话、姓名等信息。"
            ),
            expected_output="统一整理后的物业来电闭环结果。",
            agent=self.summary_agent(),
            context=[
                self.risk_assessment_task(),
                self.transcript_task(),
                self.workorder_task(),
                self.clarify_task(),
            ],
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.risk_agent(),
                self.transcript_agent(),
                self.task_agent(),
                self.clarify_agent(),
                self.summary_agent(),
            ],
            tasks=[
                self.risk_assessment_task(),
                self.transcript_task(),
                self.workorder_task(),
                self.clarify_task(),
                self.final_summary_task(),
            ],
            process=Process.sequential,
            verbose=True,
        )