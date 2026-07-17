"""RAG 相关 Agent 工具：search_knowledge + web_search。"""

from app.core.tools.base import BaseTool, DangerLevel, ToolParameter
from app.rag.document import KnowledgeBase


class SearchKnowledgeTool(BaseTool):
    """搜索本地知识库。"""

    name = "search_knowledge"
    description = (
        "搜索本地知识库，获取与查询相关的文档片段。当用户询问需要参考文档、"
        "技术资料、项目上下文等内容时使用此工具。"
    )

    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="搜索查询字符串",
        ),
        ToolParameter(
            name="top_k",
            type="integer",
            description="返回结果数量，默认 3，最大 10",
            required=False,
        ),
    ]
    danger_level = DangerLevel.SAFE

    def __init__(self, kb: KnowledgeBase | None = None):
        self.kb = kb or KnowledgeBase()

    def execute(self, query: str, top_k: int = 3) -> str:
        top_k = min(max(top_k, 1), 10)
        results = self.kb.search(query, k=top_k)

        if not results:
            return "知识库为空或未找到相关结果。"

        lines = [f"找到 {len(results)} 条相关知识：\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"--- [{i}] 来源: {r['source']} ---")
            lines.append(r["text"])
            lines.append("")
        return "\n".join(lines)


class WebSearchTool(BaseTool):
    """网络搜索工具（使用 DuckDuckGo，无需 API key）。"""

    name = "web_search"
    description = (
        "搜索互联网获取实时信息。当用户询问最新新闻、实时数据、"
        "或本地知识库无法回答的问题时使用。"
    )

    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="搜索查询字符串",
        ),
        ToolParameter(
            name="num_results",
            type="integer",
            description="返回结果数量，默认 3，最大 5",
            required=False,
        ),
    ]
    danger_level = DangerLevel.READ_ONLY

    def execute(self, query: str, num_results: int = 3) -> str:
        num_results = min(max(num_results, 1), 5)

        try:
            from duckduckgo_search import DDGS
            results = list(DDGS().text(query, max_results=num_results))
        except ImportError:
            # Fallback: requests + BeautifulSoup 直接抓取
            try:
                import requests
                from bs4 import BeautifulSoup
                import urllib.parse

                url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
                resp = requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (XinBot)"
                })
                soup = BeautifulSoup(resp.text, "lxml")
                result_elements = soup.select(".result")[:num_results]

                results = []
                for el in result_elements:
                    title_el = el.select_one(".result__title")
                    snippet_el = el.select_one(".result__snippet")
                    link_el = el.select_one(".result__url")
                    results.append({
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "body": snippet_el.get_text(strip=True) if snippet_el else "",
                        "href": link_el.get_text(strip=True) if link_el else "",
                    })
            except ImportError:
                return "网络搜索功能需要 duckduckgo-search 或 requests+beautifulsoup4 库。"
            except Exception as e:
                return f"搜索失败: {e}"

        if not results:
            return f"未找到关于 '{query}' 的搜索结果。"

        lines = [f"搜索 '{query}' 的结果：\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            lines.append(f"[{i}] {title}")
            if body:
                lines.append(f"    {body[:300]}")
            if href:
                lines.append(f"    🔗 {href}")
            lines.append("")
        return "\n".join(lines)

