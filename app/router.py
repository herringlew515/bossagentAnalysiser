import json
import re


class IntentRouter:
    def __init__(self, settings, llm):
        self.settings, self.llm = settings, llm

    def route(self, question, mode="auto"):
        if mode != "auto":
            return mode, "使用手动选择的问答模式"
        if re.search(r"平均|均薪|中位数|统计|多少|数量|总数|占比|比例|排名|排行|分布|最高|最低|薪资|工资|薪水|列出|筛选|前\s*\d+|top\s*\d+", question, re.I):
            return "sql", "问题涉及统计、薪资或岗位数据筛选"
        if re.search(r"技能|要求|需要|如何|怎么|学习|准备|职责|知识|面试|能力|区别|建议|技术栈", question):
            return "rag", "问题涉及岗位要求、技能或就业知识"
        if self.settings.llm_ready:
            result = self.llm.chat([
                {"role": "system", "content": '判断就业问题路由。数量、薪资、聚合、筛选走 sql；技能、岗位要求、知识问答走 rag。只输出 JSON：{"route":"rag或sql"}。'},
                {"role": "user", "content": question},
            ])
            try:
                route = json.loads(result)["route"]
                if route in ("rag", "sql"):
                    return route, "模型根据问题语义选择处理路径"
            except (ValueError, KeyError, TypeError):
                pass
        return "rag", "默认检索岗位资料，可手动切换为数据查询"
