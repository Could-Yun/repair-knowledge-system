"""
LLM 服务封装（SKILL 07 / SKILL 10）

三通道路由：
  - chat()             → CHAT 通道（DeepSeek 文本对话）→ 云端失败降级 local
  - describe_images()  → VL   通道（Qwen-VL-Max 多模态）→ 失败返回空串（不阻塞主流程）
  - extract_triplets() → CHAT 通道（沿用文本对话能力）

云端全挂时统一兜底到本地 llama.cpp（OpenAI 兼容接口）
LoongArch 兼容：纯 HTTP 调用，无架构依赖
"""
import os
import base64
import re
import time
import json
import httpx
from typing import List, Optional

from app.config import settings
from app.utils.logger import llm_logger, logger


# ----------------------------------------------------------------------
# 诊断结构化输出（SKILL 07 §3.1 / §7）
# ----------------------------------------------------------------------
DIAGNOSIS_SYSTEM_PROMPT = (
    "你是一名专业的设备检修工程师。请综合故障描述、图片分析和参考资料，给出诊断。\n"
    "【依据优先级】\n"
    "  1. 判断「是什么故障」——现场一手证据优先：用户的【故障描述】与【图片分析】是本次故障的直接证据。"
    "若【图片分析】已指出明确故障特征（如断裂、破碎、积碳、锈蚀、拉伤、金属碎屑、烧蚀变色等），"
    "必须把它作为诊断的主要依据写入 fault_analysis；绝不能忽略图片，更不能声称缺少图片佐证。\n"
    "  2. 判断「怎么修、标准值多少」——以知识库为权威基准：repair_steps、required_tools 以及任何"
    "规格数值（间隙、扭矩、压力、温度阈值等）应【优先采用】下方【参考资料】中手册/案例的内容；"
    "手册未覆盖时才用通用检修经验补充，并在该步注明「（手册未覆盖，依据通用经验）」。"
    "不得编造手册中不存在的具体数值。与本次故障无关的参考资料必须忽略。\n"
    "  3. 只有当现场证据（描述+图片）与参考资料都不足以定位时，才据通用检修经验给出、把 confidence 调低，"
    "并在 fault_analysis 说明依据不足。\n"
    "【引用溯源（重要）】参考资料以【参考资料N】标注（N 为序号）。当某条结论或步骤来自某条参考资料时，"
    "在该句【句末】追加形如 [来源N] 的标注（可多个，如 [来源1][来源3]）；并在 citations 中列出真正用到的 N。"
    "不要给未使用的资料编号。\n"
    "必须只输出一个 JSON 对象（不要任何额外文字、不要 markdown 代码块），字段如下：\n"
    "{\n"
    '  "fault_analysis": "故障原因分析（字符串，100-300字，含 [来源N] 标注）",\n'
    '  "repair_steps": ["检修步骤1（可含 [来源N]）", "检修步骤2", "..."],\n'
    '  "required_tools": ["工具1", "工具2"],\n'
    '  "safety_risks": ["风险或注意事项1", "..."],\n'
    '  "confidence": 0.0~1.0 的数字,\n'
    '  "related_case_ids": ["参考资料中 [ID:xxx] 里真正相关的 id"],\n'
    '  "citations": [真正引用到的参考资料序号N（整数）]\n'
    "}\n"
    "若信息不足，confidence 给低值并在 fault_analysis 中说明。related_case_ids 只能取参考资料中出现过的 ID。"
)


# ----------------------------------------------------------------------
# 分步检修向导（逐步排查：系统给一步 → 用户反馈 → 排除/确认 → 下一步）
# ----------------------------------------------------------------------
GUIDE_SYSTEM_PROMPT = (
    "你是一名资深设备检修工程师，正在通过对讲一步一步指导一线检修人员现场排查故障。\n"
    "【最高准则】必须以提供的《检修手册依据》为权威基准来设计每一步检查：\n"
    "  - 手册中给出的检查项目、判定标准、规格数值、拆装顺序要优先采用，并在 action/expected 中"
    "尽量引用手册里的具体标准（如间隙值、压力范围、温度阈值等）。\n"
    "  - 只有当手册依据未覆盖当前情形时，才用通用检修经验补充，并在 purpose 里注明“（手册未覆盖，"
    "依据通用经验）”。\n"
    "  - 不得编造手册中不存在的具体数值；不确定的数值用定性描述。\n"
    "排查规则：\n"
    "1. 每次只给【一个】最关键、最容易执行的检查或操作，遵循“先易后难、先高概率后低概率、先安全后拆解”。\n"
    "2. 收到用户对上一步的反馈后，先判断该反馈能排除或确认哪些可能原因（写入 ruled_out），再据此决定下一步；"
    "不要重复已做过的检查，也不要换汤不换药。\n"
    "【排除铁律】只有某项检查反馈为“正常”，才能把该项对应的原因写入 ruled_out；"
    "反馈为“异常”是支持/指向某原因的证据，绝不能据此把相关原因写入 ruled_out，反而要把它作为高度怀疑项保留；"
    "ruled_out 中的任何一项都不得与已反馈为“异常”的现场发现相矛盾（例如：机油品质异常时，绝不能排除“润滑/机油相关”的原因）。\n"
    "【异常深挖·必须收敛】一旦某步反馈为“异常”，下一步必须紧扣该异常、深入排查它的【直接根因】"
    "（例如：缸压异常→查活塞环/气门密封/缸壁拉伤；机油品质异常→查污染来源与机油上窜路径），"
    "严禁撇开已发现的异常去开启不相关的新检查方向。每当已有的“异常”发现合在一起已能合理指向某一根本原因时，"
    "立即把 is_final 置为 true 给出结论，不要无谓地继续加步骤拖延；正常情况下总步数不应超过 4~5 步即应收敛定论。\n"
    "3. 当已能锁定根本原因、或故障已被定位/修复、或合理原因均已排除时，把 is_final 置为 true，"
    "并在 conclusion 给出最终结论（根本原因）与处置方案。\n"
    "4. action 要具体可执行（一句话），purpose/expected 要让一线人员看得懂、能照做。\n"
    "必须只输出一个 JSON 对象（不要任何额外文字、不要 markdown 代码块），字段如下：\n"
    "{\n"
    '  "step_no": 当前步骤序号(整数, 从1开始),\n'
    '  "ruled_out": ["依据最近一次反馈排除的可能原因, 无则空数组"],\n'
    '  "action": "本步要做的具体检查或操作(一句话)",\n'
    '  "purpose": "这一步的目的: 要确认或排除什么",\n'
    '  "expected": "正常/异常时分别应观察到什么(尽量引用手册标准)",\n'
    '  "is_final": false,\n'
    '  "conclusion": "is_final=true 时填: 根本原因 + 处置方案; 否则空串",\n'
    '  "final_tools": ["is_final=true 时填: 处置所需工具"],\n'
    '  "final_safety": ["is_final=true 时填: 安全注意事项"]\n'
    "}"
)


# ----------------------------------------------------------------------
# 标准化作业指引生成（管理员审批一线申请时，AI 基于手册生成步骤草稿）
# ----------------------------------------------------------------------
REPAIR_LEVEL_ZH = {"daily": "日常保养", "minor": "小修", "major": "大修", "emergency": "急修"}

WORKFLOW_GEN_SYSTEM_PROMPT = (
    "你是一名设备检修标准化作业(SOP)编制专家。请根据给定的设备、检修等级与作业任务，"
    "结合下方《检修手册依据》，生成一份【一步一步】的标准化作业指引草稿，供管理员审核后发布。\n"
    "【要求】\n"
    "1. 步骤要符合现场实操顺序：先安全、先准备、再作业、最后验证收尾。\n"
    "2. 优先采用手册中的检查项、判定标准、规格数值、拆装顺序；手册未覆盖处用通用规范补充，不要编造具体数值。\n"
    "3. 每一步都要有明确的可执行动作描述(desc)；涉及安全/合规的步骤必须给出 checks（必须勾选确认的合规项）。\n"
    "4. 面向定期保养、清洗等任务时，强调清洁、润滑、紧固、记录与留痕。\n"
    "5. 步骤数量 4~10 步为宜。\n"
    "必须只输出一个 JSON 对象（不要任何额外文字、不要 markdown 代码块），字段如下：\n"
    "{\n"
    '  "estimated_duration": 预计耗时分钟数(整数),\n'
    '  "steps": [\n'
    '    {"step":1, "title":"步骤标题", "desc":"具体操作说明",\n'
    '     "checks":["必须勾选确认的合规/安全项1","..."], "risk":"本步主要风险(无则空串)",\n'
    '     "tools":["所需工具1","..."]}\n'
    "  ]\n"
    "}"
)


# ----------------------------------------------------------------------
# 维修作业方案生成（分步排查定论后，把「根本原因」转成「怎么修」的分步作业）
# ----------------------------------------------------------------------
REPAIR_PLAN_SYSTEM_PROMPT = (
    "你是一名资深设备检修工程师。现场已通过分步排查锁定了故障的根本原因，"
    "现在需要你把它转成一份【一步一步、可照做】的维修作业方案，交给一线人员现场执行。\n"
    "【最高准则】必须以下方《检修手册依据》为权威基准：手册中给出的拆装顺序、扭矩规格、"
    "间隙标准、更换件清单要优先采用并在 desc 中写明具体数值；手册未覆盖之处用通用检修规范补充，"
    "但严禁编造具体数值。\n"
    "【要求】\n"
    "1. 步骤必须符合现场实操顺序：安全隔离与准备 → 拆卸 → 更换/修复 → 装配 → 校验 → 收尾记录。\n"
    "2. 每一步的 desc 要具体到部件名称、动作与判定依据，让一线人员能直接照做，不要写空泛的『检查相关部件』。\n"
    "3. 凡涉及断电、泄压、高温、高处、重物、易燃介质的步骤，checks 必须给出该步开工前"
    "必须逐项确认的安全项；其余步骤的 checks 给出关键质量确认项（如扭矩已校验、间隙已复测）。\n"
    "4. tools 只列本步真正要用到的工具与量具，写明规格（如『扭矩扳手（精度±2%）』『塞尺组 0.05~0.50mm』）。\n"
    "5. risk 写本步最主要的一条风险，无则空串。\n"
    "6. 步骤数量 4~8 步为宜，不要把一个动作拆得过碎。\n"
    "必须只输出一个 JSON 对象（不要任何额外文字、不要 markdown 代码块），字段如下：\n"
    "{\n"
    '  "plan_title": "维修作业名称(一句话, 如: 更换凸轮轴总成及配套件)",\n'
    '  "estimated_duration": 预计耗时分钟数(整数),\n'
    '  "steps": [\n'
    '    {"step":1, "title":"步骤标题", "desc":"具体操作说明(含手册中的规格数值)",\n'
    '     "checks":["本步开工前必须确认的安全/质量项1","..."], "risk":"本步主要风险(无则空串)",\n'
    '     "tools":["所需工具1","..."]}\n'
    "  ]\n"
    "}"
)

class LLMService:
    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """文本对话：走 CHAT 通道，云端失败降级本地"""
        try:
            return await self._call(
                base_url=settings.CHAT_BASE_URL,
                api_key=settings.CHAT_API_KEY,
                model=model or settings.CHAT_MODEL,
                provider=settings.CHAT_PROVIDER,
                channel="chat",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=90.0,
            )
        except Exception as e:
            logger.warning(f"CHAT 云端失败 ({_short(e)}) → 降级本地 llama.cpp")
            return await self._call_local(messages, max_tokens=max_tokens)

    async def describe_images(
        self,
        image_paths: list[str],
        prompt: Optional[str] = None,
    ) -> str:
        """
        多模态视觉：走 VL 通道，看图生成文字描述
        失败返回空串（图片描述失败不应阻塞主诊断流程）
        """
        if not image_paths:
            return ""
        if not settings.VL_API_KEY:
            logger.warning("VL_API_KEY 未配置，跳过图片描述")
            return ""

        prompt = prompt or (
            "请详细描述这些图片中显示的设备故障现象，"
            "包括可见损伤、异常部位、颜色变化、磨损程度等。100-200 字。"
        )
        content_parts: list[dict] = [{"type": "text", "text": prompt}]
        for path in image_paths[:3]:  # 最多 3 张
            try:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": self._to_base64(path)},
                })
            except Exception as e:
                logger.warning(f"图片转 base64 失败: {path} | {e}")

        messages = [{"role": "user", "content": content_parts}]
        try:
            return await self._call(
                base_url=settings.VL_BASE_URL,
                api_key=settings.VL_API_KEY,
                model=settings.VL_MODEL,
                provider=settings.VL_PROVIDER,
                channel="vl",
                messages=messages,
                temperature=0.3,
                max_tokens=512,
                timeout=120.0,
            )
        except Exception as e:
            logger.warning(f"VL 云端失败 ({_short(e)})，本地无 VL 模型，返回空描述")
            return ""

    async def extract_triplets(self, text: str) -> list[dict]:
        """知识图谱三元组抽取（CHAT 通道）"""
        messages = [
            {"role": "system", "content": (
                "你是知识图谱抽取专家。请从文本中抽取三元组，格式为 JSON 数组：\n"
                '[{"subject": "实体名", "subject_type": "device|component|symptom|cause|solution|tool|part", '
                '"predicate": "has_component|symptom_of|caused_by|solved_by|requires_tool|related_to|part_of", '
                '"object": "实体名", "object_type": "...", "confidence": 0.9}]\n'
                "只返回 JSON，不要其他说明。"
            )},
            {"role": "user", "content": f"请从以下文本抽取三元组：\n{text[:2000]}"},
        ]
        try:
            resp = await self.chat(messages, temperature=0.2)
            start = resp.find("[")
            end   = resp.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(resp[start:end])
        except Exception as e:
            logger.error(f"三元组抽取失败: {e}")
        return []

    # ------------------------------------------------------------------
    # 故障诊断：结构化 Prompt + 容错解析（SKILL 07 §3.1 / §7）
    # ------------------------------------------------------------------
    @staticmethod
    def build_diagnosis_messages(
        description: str,
        img_desc: str = "",
        context: str = "",
        feedback_context: str = "",
        kg_context: str = "",
    ) -> list[dict]:
        system = DIAGNOSIS_SYSTEM_PROMPT
        if feedback_context:
            system += f"\n\n[已采纳的人工修正经验，请优先参考]\n{feedback_context}"
        user = f"**故障描述：**\n{description}\n\n"
        if img_desc:
            user += f"**图片分析：**\n{img_desc}\n\n"
        if context:
            user += f"**参考资料（手册/历史案例，标注为【参考资料N】）：**\n{context}\n"
        # 创新点 B：注入知识图谱推理线索（症状→原因→处置），辅助 LLM 推理
        if kg_context:
            user += (
                "\n**知识图谱关联线索（供推理参考，每行为一条 实体—关系→实体）：**\n"
                f"{kg_context}\n"
            )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def parse_diagnosis_response(raw: str) -> dict:
        """
        将模型输出解析为结构化字段，保证 6 个字段恒在：
          fault_analysis / repair_steps[] / required_tools[] / safety_risks[] /
          confidence / related_case_ids[]
        优先 JSON；失败则按 Markdown 段落正则兜底。
        """
        default = {
            "fault_analysis": "",
            "repair_steps": [],
            "required_tools": [],
            "safety_risks": [],
            "confidence": 0.5,
            "related_case_ids": [],
            "citations": [],
        }
        if not raw:
            return default

        # 1) JSON 优先（容错截取首个 {...}）
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
                out = dict(default)
                out["fault_analysis"]  = str(data.get("fault_analysis", "")).strip()
                out["repair_steps"]    = _as_str_list(data.get("repair_steps"))
                out["required_tools"]  = _as_str_list(data.get("required_tools"))
                out["safety_risks"]    = _as_str_list(data.get("safety_risks"))
                out["related_case_ids"]= _as_str_list(data.get("related_case_ids"))
                out["citations"]       = _as_int_list(data.get("citations"))
                try:
                    out["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
                except (TypeError, ValueError):
                    out["confidence"] = 0.5
                if out["fault_analysis"] or out["repair_steps"]:
                    return out
            except Exception:
                pass

        # 2) Markdown 兜底：按常见小标题切分
        out = dict(default)
        out["fault_analysis"] = raw.strip()[:600]
        out["repair_steps"]   = _extract_section_list(raw, ["检修步骤", "维修步骤", "处理步骤", "解决方案", "步骤"])
        out["required_tools"] = _extract_section_list(raw, ["所需工具", "工具", "需要工具"])
        out["safety_risks"]   = _extract_section_list(raw, ["注意事项", "风险", "安全"])
        return out

    # ------------------------------------------------------------------
    # 分步检修向导：消息构建 + 容错解析
    # ------------------------------------------------------------------
    @staticmethod
    def build_guide_messages(
        fault_description: str,
        fault_analysis: str = "",
        repair_steps: Optional[list] = None,
        history: Optional[list] = None,
        kb_context: str = "",
        force_conclude: bool = False,
    ) -> list[dict]:
        """history: [{action, result, note}]，result 取 正常/异常/不确定"""
        repair_steps = repair_steps or []
        history = history or []

        user = f"**故障描述：**\n{fault_description}\n\n"
        if kb_context:
            user += (
                "**【检修手册依据】（权威基准，请优先采用其中的检查项与判定标准）：**\n"
                f"{kb_context}\n\n"
            )
        if fault_analysis:
            user += f"**初步原因分析（参考）：**\n{fault_analysis}\n\n"
        if repair_steps:
            user += "**初步推荐检修步骤（参考）：**\n" + \
                "\n".join(f"- {s}" for s in repair_steps) + "\n\n"

        if history:
            user += "**已完成的检查与现场反馈：**\n"
            for i, h in enumerate(history):
                res = h.get("result", "")
                note = h.get("note", "")
                line = f"第{i+1}步：{h.get('action','')} → 反馈：{res}"
                if note:
                    line += f"（补充：{note}）"
                user += line + "\n"
            # 已做过的检查清单，明确禁止重复
            done = "、".join(h.get("action", "") for h in history if h.get("action"))
            user += f"\n【禁止重复】以下检查已完成，下一步绝不能再出现：{done}\n"
            # 已确认的异常证据：直接写进 user 消息（比 system 规则遵守度更高），强制围绕异常深挖、严禁排除
            abnormal = [h.get("action", "") for h in history if h.get("result") == "异常" and h.get("action")]
            if abnormal:
                user += (
                    "\n【已确认异常·必须保留并深挖，严禁排除】以下检查已现场反馈为“异常”，"
                    "它们对应的可能原因是当前最高怀疑，绝不能写进 ruled_out；"
                    "下一步必须紧扣这些异常、深入排查其【直接根因】，不得撇开它们去开新方向：\n"
                    + "\n".join(f"- {a}" for a in abnormal) + "\n"
                )
            if force_conclude:
                user += (
                    "\n【必须收敛】现在不要再输出新的检查步骤。请综合以上全部反馈，"
                    "把 is_final 置为 true，在 conclusion 给出最可能的根本原因与处置方案"
                    "（哪一步反馈为“异常”，通常即指向根因）。"
                )
            else:
                user += (
                    "\n请给出与上述【都不相同】的下一步检查；"
                    "若某一步反馈为“异常”且已能据此锁定根本原因，请直接 is_final=true 给出结论，不要再绕。"
                )
        else:
            user += "现在请给出【第一步】检查。"

        return [
            {"role": "system", "content": GUIDE_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def parse_guide_response(raw: str, step_no: int = 1) -> dict:
        """解析向导单步输出，保证字段恒在。"""
        default = {
            "step_no": step_no,
            "ruled_out": [],
            "action": "",
            "purpose": "",
            "expected": "",
            "is_final": False,
            "conclusion": "",
            "final_tools": [],
            "final_safety": [],
        }
        if not raw:
            return default

        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
                out = dict(default)
                try:
                    out["step_no"] = int(data.get("step_no", step_no))
                except (TypeError, ValueError):
                    out["step_no"] = step_no
                out["ruled_out"]    = _as_str_list(data.get("ruled_out"))
                out["action"]       = str(data.get("action", "")).strip()
                out["purpose"]      = str(data.get("purpose", "")).strip()
                out["expected"]     = str(data.get("expected", "")).strip()
                out["conclusion"]   = str(data.get("conclusion", "")).strip()
                out["final_tools"]  = _as_str_list(data.get("final_tools"))
                out["final_safety"] = _as_str_list(data.get("final_safety"))
                out["is_final"]     = _as_bool(data.get("is_final"))
                if out["action"] or out["conclusion"]:
                    return out
            except Exception:
                pass

        # 兜底：把整段当作 action 文本
        out = dict(default)
        out["action"] = raw.strip()[:300]
        return out

    # ------------------------------------------------------------------
    # 标准化作业指引生成
    # ------------------------------------------------------------------
    @staticmethod
    def build_workflow_messages(
        device_name: str,
        repair_level: str,
        title: str,
        description: str = "",
        kb_context: str = "",
    ) -> list[dict]:
        level_zh = REPAIR_LEVEL_ZH.get(repair_level, repair_level)
        user = (
            f"**设备**：{device_name or '（通用设备）'}\n"
            f"**检修等级**：{level_zh}\n"
            f"**作业任务**：{title}\n"
        )
        if description:
            user += f"**作业说明/背景**：{description}\n"
        if kb_context:
            user += f"\n**《检修手册依据》（请优先采用其中的检查项与标准）：**\n{kb_context}\n"
        user += "\n请据此生成标准化作业指引步骤草稿。"
        return [
            {"role": "system", "content": WORKFLOW_GEN_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def parse_workflow_response(raw: str) -> dict:
        """解析作业指引草稿，返回 {steps:[{step,title,desc,checks[],risk,tools[]}], estimated_duration}。"""
        out = {"steps": [], "estimated_duration": None}
        if not raw:
            return out
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start == -1 or end <= start:
            return out
        try:
            data = json.loads(text[start:end])
        except Exception:
            return out
        try:
            out["estimated_duration"] = int(data.get("estimated_duration"))
        except (TypeError, ValueError):
            out["estimated_duration"] = None
        steps = []
        for i, s in enumerate(data.get("steps") or []):
            if not isinstance(s, dict):
                continue
            title = str(s.get("title", "")).strip()
            desc  = str(s.get("desc", "")).strip()
            if not (title or desc):
                continue
            steps.append({
                "step":  i + 1,
                "title": title or f"步骤{i+1}",
                "desc":  desc,
                "checks": _as_str_list(s.get("checks")),
                "risk":  str(s.get("risk", "")).strip(),
                "tools": _as_str_list(s.get("tools")),
            })
        out["steps"] = steps
        return out

    async def generate_workflow(
        self,
        device_name: str,
        repair_level: str,
        title: str,
        description: str = "",
        kb_context: str = "",
    ) -> dict:
        """调用 CHAT 通道生成作业指引草稿（云端失败自动降级本地）。"""
        messages = self.build_workflow_messages(device_name, repair_level, title, description, kb_context)
        raw = await self.chat(messages, temperature=0.3, max_tokens=2048)
        return self.parse_workflow_response(raw)

    @staticmethod
    def build_repair_plan_messages(
        device_name: str,
        fault_description: str,
        root_cause: str,
        guide_history: Optional[list] = None,
        kb_context: str = "",
    ) -> list[dict]:
        """把排查定论 + 手册依据组装成维修方案生成的提示词。"""
        user = (
            f"**设备**：{device_name or '（通用设备）'}\n"
            f"**故障现象**：{fault_description}\n"
            f"**已确认的根本原因**：{root_cause}\n"
        )
        if guide_history:
            lines = []
            for h in guide_history:
                act = str(h.get("action", "")).strip()
                res = str(h.get("result", "")).strip()
                note = str(h.get("note", "")).strip()
                if act:
                    lines.append(f"- {act} → {res}" + (f"（{note}）" if note else ""))
            if lines:
                user += "\n**现场排查过程（用于判断哪些部位已确认状态）**：\n" + "\n".join(lines) + "\n"
        if kb_context:
            user += f"\n**《检修手册依据》（请优先采用其中的拆装顺序与规格数值）：**\n{kb_context}\n"
        user += "\n请据此生成现场可执行的维修作业方案。"
        return [
            {"role": "system", "content": REPAIR_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    async def generate_repair_plan(
        self,
        device_name: str,
        fault_description: str,
        root_cause: str,
        guide_history: Optional[list] = None,
        kb_context: str = "",
    ) -> dict:
        """调用 CHAT 通道生成维修作业方案（云端失败自动降级本地）。
        复用 parse_workflow_response 的解析与字段结构，前端执行引擎可直接复用。"""
        messages = self.build_repair_plan_messages(
            device_name, fault_description, root_cause, guide_history, kb_context)
        raw = await self.chat(messages, temperature=0.3, max_tokens=2048)
        out = self.parse_workflow_response(raw)
        # plan_title 不在 parse_workflow_response 的字段里，单独取一次
        try:
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
            st, en = text.find("{"), text.rfind("}") + 1
            if st != -1 and en > st:
                out["plan_title"] = str(json.loads(text[st:en]).get("plan_title", "")).strip()
        except Exception:
            out["plan_title"] = ""
        if not out.get("plan_title"):
            out["plan_title"] = "现场维修作业"
        return out

    async def health(self) -> dict:
        """LLM 通道健康检查（SKILL 07 §1.3）"""
        chat_ok = await _ping(settings.CHAT_BASE_URL, settings.CHAT_API_KEY)
        vl_ok   = await _ping(settings.VL_BASE_URL,   settings.VL_API_KEY)
        local_ok= await _ping(settings.LOCAL_LLM_URL, settings.LOCAL_LLM_KEY)
        return {
            "chat":  {"provider": settings.CHAT_PROVIDER, "model": settings.CHAT_MODEL,
                      "status": "ok" if chat_ok else "down"},
            "vl":    {"provider": settings.VL_PROVIDER,   "model": settings.VL_MODEL,
                      "status": "ok" if vl_ok   else "down"},
            "local": {"model": settings.LOCAL_LLM_MODEL,
                      "status": "ok" if local_ok else "down"},
            "primary": "cloud" if chat_ok else ("local" if local_ok else "all-down"),
        }

    # ------------------------------------------------------------------
    # 内部：统一 HTTP 调用（兼容 OpenAI / DeepSeek / DashScope 兼容模式）
    # ------------------------------------------------------------------
    @staticmethod
    async def _call(
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider: str,
        channel: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> str:
        if not api_key:
            raise RuntimeError(f"{channel.upper()} 通道未配置 API key（provider={provider}）")

        t0 = time.time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            llm_logger.info(
                f"channel={channel} provider={provider} model={model} "
                f"latency={time.time()-t0:.2f}s "
                f"tokens={data.get('usage', {}).get('total_tokens', '?')}"
            )
            return content

    async def _call_local(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """本地 llama.cpp 兜底（SKILL 10 §2.3）"""
        try:
            return await self._call(
                base_url=settings.LOCAL_LLM_URL,
                api_key=settings.LOCAL_LLM_KEY,
                model=settings.LOCAL_LLM_MODEL,
                provider="llama.cpp",
                channel="local",
                messages=messages,
                temperature=0.5,
                max_tokens=max_tokens,
                timeout=180.0,
            )
        except Exception as e:
            logger.error(f"本地 LLM 也失败: {_short(e)}")
            raise RuntimeError(
                "云端与本地大模型均不可用。请检查 CHAT_API_KEY 配置或启动 llama-server。"
            ) from e

    @staticmethod
    def _to_base64(path: str) -> str:
        # 兼容传入的是 URL 路径(/uploads/...)：解析到 UPLOAD_DIR 下的真实磁盘文件
        if not os.path.exists(path) and path.startswith("/uploads/"):
            path = os.path.join(settings.UPLOAD_DIR, path.replace("/uploads/", "", 1))
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext  = path.split(".")[-1].lower()
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f"data:image/{mime};base64,{b64}"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _short(e: Exception, n: int = 160) -> str:
    s = str(e).strip().splitlines()[0]
    return (s[:n] + "...") if len(s) > n else s


def _as_str_list(v) -> list[str]:
    """把任意值规整为非空字符串列表"""
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def _as_int_list(v) -> list[int]:
    """把任意值规整为去重的正整数列表（用于 citations 引用序号）"""
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        v = [v]
    out: list[int] = []
    for x in v:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in out:
            out.append(n)
    return out


def _as_bool(v) -> bool:
    """容错布尔：兼容 true/false、"true"/"false"、1/0、是/否"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y", "是", "对")
    return False


def _extract_section_list(text: str, headers: list[str]) -> list[str]:
    """从 Markdown 文本中按小标题抽取其后的列表项（- / 1. / • 开头）"""
    lines = text.splitlines()
    collecting = False
    items: list[str] = []
    for line in lines:
        s = line.strip()
        if any(h in s for h in headers) and (s.endswith("：") or s.endswith(":") or "**" in s or s.startswith("#")):
            collecting = True
            continue
        if collecting:
            if not s:
                continue
            m = re.match(r"^(?:[-*•]|\d+[.)、])\s*(.+)$", s)
            if m:
                items.append(m.group(1).strip())
            elif s.startswith("#") or s.startswith("**"):
                break  # 进入下一节
    return items


async def _ping(base_url: str, api_key: str) -> bool:
    if not api_key:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # /models 是 OpenAI 兼容协议的轻量探测端点
            r = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return r.status_code < 500
    except Exception:
        return False
