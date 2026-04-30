from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import requests

class MyCustomToolInput(BaseModel):
    """Input schema for MyCustomTool."""
    argument: str = Field(..., description="Description of the argument.")

class MyCustomTool(BaseTool):
    name: str = "Name of my tool"
    description: str = (
        "Clear description for what this tool is useful for, your agent will need this information to use it."
    )
    args_schema: Type[BaseModel] = MyCustomToolInput

    def _run(self, argument: str) -> str:
        # Implementation goes here
        return "this is an example of a tool output, ignore it and move along."


class search_arxiv(BaseTool):
    name: str = "search_arxiv"
    description: str = (
        "Search latest papers from arXiv"
    )
    args_schema: Type[BaseModel] = MyCustomToolInput

    def _run(self, query: str) -> str:
        # Implementation goes here
        url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"
        response = requests.get(url)
        return response.text



from crewai_tools import tool

@tool("简单日志工具")
def simple_log_tool(text: str) -> str:
    """用于记录日志或调试"""
    return f"日志记录: {text}"
