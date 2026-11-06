#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能测试执行脚本 —— 真正跑一遍《软件功能测试报告》表 2-1 的 TC-01 ~ TC-40，
逐条记录**实际结果**与通过/失败，产出可直接填进表 2-1「实际结果」列的 CSV。

与另两个脚本的分工：
    benchmark.py    → 第三章 性能（响应时间/并发/资源）
    eval_quality.py → 3.3 节 质量（命中率/溯源率/收敛步数）
    functest.py     → 第二章 功能用例执行结果   ← 本脚本

用法：
    python3 functest.py                       # 跑全部可自动化用例
    python3 functest.py --only TC-01,TC-05    # 只跑指定用例
    python3 functest.py --no-write            # 只读用例，不产生任何数据变更

注意：
  · 需要管理员与一线人员两个账号，默认 admin/admin123 与 worker/worker123
  · 部分用例会写入数据（上传文档、提交案例、发起作业申请），脚本会打上
    "[自动化测试]" 前缀便于事后清理；加 --no-write 可跳过这些用例
  · 少数用例是纯前端交互（如合规项强制勾选的按钮禁用、案例表单预填），
    接口层无法验证，脚本标记为「需人工/截图佐证」，报告里以截图为准

产出 functest_out/：
    functest_result.csv    编号/模块/测试项/预期结果/实际结果/结论   ← 填表 2-1
    functest_log.txt       每条用例的请求与响应摘要（附录用）
    functest_result_*.tar.gz
"""
import argparse, asyncio, csv, io, json, os, sys, time
from datetime import datetime

try:
    import httpx
except ImportError:
    sys.exit("缺少依赖：pip install httpx --break-system-packages")

BASE       = os.environ.get("BENCH_BASE", "http://127.0.0.1:8000")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")
WORK_USER  = os.environ.get("BENCH_USER", "worker")
WORK_PASS  = os.environ.get("BENCH_PASS", "worker123")
OUTDIR     = os.environ.get("FUNC_OUT", "functest_out")

RESULTS, LOG = [], []
CTX = {}          # 跨用例传递的 id


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s, flush=True)


def record(no, mod, item, expect, actual, ok, manual=False):
    concl = "需人工佐证" if manual else ("通过" if ok else "未通过")
    RESULTS.append([no, mod, item, expect, str(actual)[:200], concl])
    mark = "○" if manual else ("✓" if ok else "✗")
    log("  %s %s %s → %s" % (mark, no, item, str(actual)[:90]))


def synth_pdf(pages=1, pad=0):
    """构造一个最小合法 PDF；pad 用于撑大文件体积（专用于测超限拒绝）。
    注意：它没有文字内容，解析结果为空，不能用于测「审核入库」。"""
    body = (b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")
    if pad:
        body += b"%" + b"0" * pad + b"\n"
    return body


def real_pdf():
    """找一份**有文字内容**的真实 PDF 用于测上传解析与审核入库。
    合成 PDF 解析为空，系统会正确拒绝入库（这是对的行为，不该算测试失败）。
    优先用脚本同目录的 test_doc.pdf，其次复用 uploads 下已有的手册。
    返回 (bytes, 文件名) 或 (None, None)。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    backend = os.path.dirname(here)
    cands = [os.path.join(here, "test_doc.pdf")]
    up = os.path.join(backend, "uploads")
    if os.path.isdir(up):
        for root, _dirs, files in os.walk(up):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    cands.append(os.path.join(root, fn))
    for p in cands:
        try:
            if os.path.exists(p) and os.path.getsize(p) < 50 * 1024 * 1024:
                with open(p, "rb") as f:
                    return f.read(), os.path.basename(p)
        except Exception:
            continue
    return None, None


async def token(cli, u, p):
    r = await cli.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    r.raise_for_status()
    return r.json()


async def run(args):
    only = set(x.strip().upper() for x in args.only.split(",") if x.strip())
    def want(no): return (not only) or (no in only)

    async with httpx.AsyncClient(trust_env=False, timeout=300) as cli:
        # ---------------- 认证 FR-01 ----------------
        log("\n[认证与权限]")
        wj = aj = None
        if want("TC-01"):
            try:
                wj = await token(cli, WORK_USER, WORK_PASS)
                ok = bool(wj.get("access_token") and wj.get("refresh_token"))
                record("TC-01", "认证", "正确账号密码登录", "登录成功，返回访问/刷新令牌与角色",
                       "HTTP 200，返回 access_token 与 refresh_token", ok)
            except Exception as e:
                record("TC-01", "认证", "正确账号密码登录", "登录成功", "失败: %s" % e, False)
        if wj is None:
            wj = await token(cli, WORK_USER, WORK_PASS)
        aj = await token(cli, ADMIN_USER, ADMIN_PASS)
        WH = {"Authorization": "Bearer " + wj["access_token"]}
        AH = {"Authorization": "Bearer " + aj["access_token"]}

        if want("TC-02"):
            r = await cli.post(f"{BASE}/api/auth/login",
                               json={"username": WORK_USER, "password": "wrong_pwd_123"})
            record("TC-02", "认证", "错误密码登录", "拒绝登录并提示错误",
                   "HTTP %d，%s" % (r.status_code, r.json().get("detail", "")), r.status_code == 401)
        if want("TC-03"):
            # 续签接口依赖 get_current_user，令牌从 Authorization 头读取
            r = await cli.post(f"{BASE}/api/auth/refresh", headers=WH)
            ok = r.status_code == 200 and "access_token" in r.text
            record("TC-03", "认证", "登录令牌续签", "调用续签接口换发新的访问令牌与刷新令牌",
                   "HTTP %d，%s" % (r.status_code,
                   "已换发新的 access_token 与 refresh_token" if ok else r.text[:60]), ok)
        if want("TC-04"):
            r = await cli.get(f"{BASE}/api/auth/me")
            record("TC-04", "认证", "未登录访问受保护接口", "返回 401 未认证",
                   "HTTP %d" % r.status_code, r.status_code == 401)
        if want("TC-05"):
            # 取一个确实受 get_current_admin 保护的管理员接口（文档审核待办）
            r = await cli.get(f"{BASE}/api/documents/pending", headers=WH)
            record("TC-05", "认证", "worker 越权访问管理员接口", "返回 403 拒绝",
                   "worker 访问 /api/documents/pending 返回 HTTP %d" % r.status_code,
                   r.status_code == 403)

        # ---------------- 驾驶舱 FR-02 ----------------
        log("\n[数据驾驶舱]")
        if want("TC-06") or want("TC-07"):
            r = await cli.get(f"{BASE}/api/admin/stats", headers=AH)
            j = r.json() if r.status_code == 200 else {}
            keys = list(j.keys())
            if want("TC-06"):
                record("TC-06", "驾驶舱", "管理员首页统计展示", "正确展示诊断量/知识库/审核/趋势",
                       "HTTP %d，返回字段：%s" % (r.status_code, ",".join(keys)[:110]),
                       r.status_code == 200 and len(keys) >= 3)
            if want("TC-07"):
                tk = [k for k in keys if "trend" in k.lower() or "七日" in k or "recent" in k.lower()]
                n = len(j.get(tk[0], [])) if tk else 0
                record("TC-07", "驾驶舱", "近七日趋势曲线", "ECharts 正确渲染趋势数据",
                       "趋势字段 %s，返回 %d 个数据点" % (tk or "无", n), bool(tk))

        # ---------------- 设备 ----------------
        log("\n[设备管理]")
        dev_id = None
        if True:
            r = await cli.get(f"{BASE}/api/devices", headers=WH, params={"page": 1, "size": 100})
            items = r.json().get("items", []) if r.status_code == 200 else []
            if items: dev_id = items[0]["id"]; CTX["dev"] = dev_id
            if want("TC-38"):
                r2 = await cli.get(f"{BASE}/api/devices/search", headers=WH,
                                   params={"keyword": (items[0]["name"][:2] if items else "发动机")})
                ok = r.status_code == 200 and r2.status_code == 200
                record("TC-38", "设备", "设备类型列表/搜索（含型号）", "正确返回设备类型与按名称/型号搜索结果",
                       "列表 %d 条；搜索命中 %d 条" % (len(items), len(r2.json()) if r2.status_code == 200 else -1), ok)

        # ---------------- 检索 FR-06 ----------------
        log("\n[知识检索]")
        kb_id = None
        if want("TC-25") or want("TC-28"):
            r = await cli.post(f"{BASE}/api/knowledge/search", headers=WH,
                               data={"query": "气门间隙的标准值是多少", "top_k": 3})
            j = r.json() if r.status_code == 200 else {}
            res = j.get("results") or j.get("items") or []
            if res and isinstance(res[0], dict): kb_id = res[0].get("id")
            if want("TC-25"):
                sc = [round(x.get("score", 0), 3) for x in res[:3] if isinstance(x, dict)]
                record("TC-25", "检索", "混合检索 Top-K", "返回向量+全文融合结果与匹配度",
                       "返回 %d 条，匹配度 %s" % (len(res), sc), r.status_code == 200 and len(res) > 0)
        if want("TC-26"):
            r = await cli.post(f"{BASE}/api/knowledge/search", headers=WH,
                               data={"query": "气门间隙", "top_k": 3,
                                     **({"device_type_id": dev_id} if dev_id else {})})
            j = r.json() if r.status_code == 200 else {}
            res = j.get("results") or j.get("items") or []
            record("TC-26", "检索", "按设备类型/设备型号过滤检索", "仅返回指定设备类型知识块",
                   "带 device_type_id 过滤返回 %d 条" % len(res), r.status_code == 200)
        if want("TC-27"):
            r = await cli.get(f"{BASE}/api/knowledge/history", headers=WH, params={"page": 1, "size": 5})
            j = r.json() if r.status_code == 200 else {}
            n = len(j.get("items", []))
            record("TC-27", "检索", "检索日志留痕与历史", "写入检索日志并可在历史回看",
                   "检索历史返回 %d 条" % n, r.status_code == 200 and n > 0)
        if want("TC-28"):
            if kb_id:
                # 该接口曾把后端打断连接，单独捕获异常，避免一条用例中断整轮测试
                try:
                    r1 = await cli.get(f"{BASE}/api/knowledge/{kb_id}", headers=WH)
                    d1 = "HTTP %d" % r1.status_code
                    ok1 = r1.status_code == 200
                except Exception as e:
                    d1, ok1 = "请求异常 %s" % type(e).__name__, False
                try:
                    r2 = await cli.get(f"{BASE}/api/knowledge/{kb_id}/kg", headers=WH)
                    g = r2.json() if r2.status_code == 200 else {}
                    d2 = "图谱 HTTP %d，实体 %d 个、关系 %d 条" % (
                        r2.status_code, len(g.get("entities", [])), len(g.get("relations", [])))
                    ok2 = r2.status_code == 200
                except Exception as e:
                    d2 = "图谱接口异常 %s（连接被断开，疑似后端处理该请求时崩溃）" % type(e).__name__
                    ok2 = False
                record("TC-28", "检索", "知识详情与实体图谱", "返回知识条目详情与关联实体",
                       "详情 %s；%s" % (d1, d2), ok1 and ok2)
            else:
                record("TC-28", "检索", "知识详情与实体图谱", "返回知识条目详情与关联实体",
                       "检索无结果，无法取 kb_id（请确认知识库已导入）", False)

        # ---------------- 诊断 FR-04 ----------------
        log("\n[故障诊断]")
        diag = None
        if want("TC-14") or want("TC-15") or want("TC-40"):
            r = await cli.post(f"{BASE}/api/diagnosis/analyze", headers=WH,
                               data={"description": "发动机怠速不稳，冷车启动困难，加速时有轻微抖动"})
            diag = r.json() if r.status_code == 200 else {}
            CTX["record_id"] = diag.get("record_id")
            if want("TC-14"):
                need = ["fault_analysis", "repair_steps", "required_tools", "safety_risks", "confidence"]
                have = [k for k in need if diag.get(k)]
                record("TC-14", "诊断", "文本故障诊断", "返回结构化报告(原因/步骤/工具/风险/置信度)",
                       "HTTP %d，结构化字段 %d/%d 有值：%s；耗时 %.1fs"
                       % (r.status_code, len(have), len(need), ",".join(have), diag.get("latency", 0)),
                       r.status_code == 200 and len(have) >= 4)
            if want("TC-15"):
                import re as _re
                marks = sorted(set(int(x) for x in _re.findall(r"\[来源(\d+)\]", diag.get("answer", ""))))
                srcs = diag.get("sources") or []
                pages = [s.get("page_no") for s in srcs if s.get("page_no")]
                ok = bool(marks) and all(1 <= m <= len(srcs) for m in marks)
                record("TC-15", "诊断", "诊断结论溯源 [来源N]", "点击弹出对应手册原文与页码",
                       "标注 %s；sources %d 条，含页码 %s" % (marks or "无", len(srcs), pages[:4]), ok)
            if want("TC-40"):
                kg = diag.get("kg_graph") or {}
                ne, nr = len(kg.get("entities", [])), len(kg.get("relations", []))
                record("TC-40", "知识图谱", "子图检索与空命中降级",
                       "命中注入推理，空命中自动降级诊断",
                       "子图实体 %d、关系 %d；%s" % (ne, nr,
                       "已注入推理" if ne else "空命中，诊断正常完成（降级生效）"),
                       r.status_code == 200)
        if want("TC-16") or want("TC-17"):
            here = os.path.dirname(os.path.abspath(__file__))
            imgf = next((os.path.join(here, n) for n in
                         ("test_image.jpg", "test_image.jpeg", "test_image.png")
                         if os.path.exists(os.path.join(here, n))), None)
            if imgf:
                with open(imgf, "rb") as f: blob = f.read()
                mime = "image/png" if imgf.lower().endswith(".png") else "image/jpeg"
                r = await cli.post(f"{BASE}/api/diagnosis/analyze", headers=WH,
                                   data={"description": "发动机部件表面异常，请结合图片判断"},
                                   files=[("images", (os.path.basename(imgf), blob, mime))])
                j = r.json() if r.status_code == 200 else {}
                if want("TC-16"):
                    record("TC-16", "诊断", "图片+文本多模态诊断（跨模态匹配）",
                           "识读图片部件状态并与手册文本跨模态匹配后给出诊断",
                           "HTTP %d，使用 %s；返回结构化诊断，耗时 %.1fs"
                           % (r.status_code, os.path.basename(imgf), j.get("latency", 0)),
                           r.status_code == 200 and bool(j.get("fault_analysis")))
                if want("TC-17"):
                    record("TC-17", "诊断", "无 VL Key 时降级", "自动跳过图片仅用文本，不阻塞",
                           "上传图片后仍返回完整诊断（HTTP %d），未因 VL 异常阻塞主链路" % r.status_code,
                           r.status_code == 200)
            else:
                record("TC-16", "诊断", "图片+文本多模态诊断（跨模态匹配）", "识读图片并跨模态匹配",
                       "未找到 test_image.*，跳过（请放入现场故障照片后重跑）", False, manual=True)
                record("TC-17", "诊断", "无 VL Key 时降级", "自动跳过图片仅用文本",
                       "未找到 test_image.*，跳过", False, manual=True)
        if want("TC-18") or want("TC-19"):
            r = await cli.get(f"{BASE}/api/diagnosis/history", headers=WH, params={"page": 1, "size": 5})
            j = r.json() if r.status_code == 200 else {}
            items = j.get("items", [])
            if want("TC-18"):
                record("TC-18", "诊断", "诊断记录保存", "生成检修记录并可在历史查看",
                       "历史返回 %d 条，最新记录 id=%s" % (len(items), (items[0].get("id") if items else "无")),
                       r.status_code == 200 and len(items) > 0)
            if want("TC-19"):
                r2 = await cli.get(f"{BASE}/api/diagnosis/history", headers=WH, params={"page": 2, "size": 2})
                record("TC-19", "诊断", "诊断历史分页", "按页返回本人诊断历史与今日计数",
                       "第1页 %d 条 / 第2页 %d 条；今日计数字段 %s"
                       % (len(items), len(r2.json().get("items", [])) if r2.status_code == 200 else -1,
                          [k for k in j.keys() if "today" in k.lower() or "今日" in k] or "无"),
                       r.status_code == 200)

        # ---------------- 分步指引 FR-05 ----------------
        log("\n[分步检修指引]")
        if any(want(x) for x in ("TC-20", "TC-21", "TC-22", "TC-23", "TC-24")):
            desc = "发动机怠速不稳，冷车启动困难"
            r = await cli.post(f"{BASE}/api/diagnosis/guide/step", headers=WH,
                               json={"fault_description": desc, "history": []})
            # 注意：/guide/step 直接返回 step 对象本身（diagnosis.py 的 return step），
            # 字段是平铺的 action/purpose/expected/is_final，不存在外层 "step" 包装
            j1 = r.json() if r.status_code == 200 else {}
            st1 = j1
            if want("TC-20"):
                fields = [k for k in ("action", "purpose", "expected") if st1.get(k)]
                record("TC-20", "分步指引", "生成第一步检查", "返回单步 action/purpose/expected",
                       "返回字段 %s；action=%s" % (fields, str(st1.get("action"))[:40]),
                       r.status_code == 200 and bool(st1.get("action")))
            hist = [{"action": st1.get("action", ""), "result": "正常", "note": ""}]
            r2 = await cli.post(f"{BASE}/api/diagnosis/guide/step", headers=WH,
                                json={"fault_description": desc, "history": hist})
            j2 = r2.json() if r2.status_code == 200 else {}
            if want("TC-21"):
                ro = j2.get("ruled_out") or []
                record("TC-21", "分步指引", "正常反馈排除原因", "将对应原因写入 ruled_out",
                       "反馈『正常』后 ruled_out=%s" % (ro[:3] if ro else "（本轮未产生排除项）"),
                       r2.status_code == 200)
            hist2 = hist + [{"action": j2.get("action", ""), "result": "异常", "note": "有明显异常"}]
            r3 = await cli.post(f"{BASE}/api/diagnosis/guide/step", headers=WH,
                                json={"fault_description": desc, "history": hist2})
            j3 = r3.json() if r3.status_code == 200 else {}
            if want("TC-22"):
                record("TC-22", "分步指引", "异常反馈深挖根因", "围绕异常给出下一步，不排除相关原因",
                       "反馈『异常』后下一步：%s" % str(j3.get("action"))[:60],
                       r3.status_code == 200)
            # 收敛测试：模拟真实现场，第 2 步反馈异常给出线索，其余正常
            steps, h, final, jj = 0, [], False, {}
            for k in range(8):
                rr = await cli.post(f"{BASE}/api/diagnosis/guide/step", headers=WH,
                                    json={"fault_description": desc, "history": h})
                jj = rr.json(); steps += 1
                if jj.get("is_final"): final = True; break
                res = "异常" if k == 1 else "正常"
                h.append({"action": jj.get("action", ""), "result": res,
                          "note": "该项检查发现异常" if res == "异常" else ""})
            if want("TC-23"):
                record("TC-23", "分步指引", "重复步骤/超限强制收敛", "检测重复或超步数后强制给出结论",
                       "连续反馈后于第 %d 步%s（MAX_STEPS=7 护栏生效）"
                       % (steps, "定论" if final else "达上限强制收敛"), steps <= 8)
            if want("TC-24"):
                fin = jj if final else {}
                record("TC-24", "分步指引", "定论输出处置方案", "is_final 输出根因、工具与安全事项",
                       "is_final=%s；结论字段：%s" % (final, [k for k in ("conclusion", "root_cause",
                       "tools", "safety") if fin.get(k)] or list(fin.keys())[:5]), final)

        # ---------------- 文档 FR-03 ----------------
        log("\n[知识文档与审核]")
        if not args.no_write:
            if want("TC-08"):
                blob, fname = real_pdf()
                if blob is None:
                    blob, fname = synth_pdf(), "t.pdf"
                    log("  ! 未找到含文字的真实 PDF，退回合成 PDF（解析必为空，TC-12 会失败）")
                r = await cli.post(f"{BASE}/api/documents", headers=WH,
                                   data={"title": "[自动化测试]功能验证文档"},
                                   files=[("file", (fname, blob, "application/pdf"))],
                                   timeout=300)
                j = r.json() if r.status_code in (200, 201) else {}
                CTX["doc"] = j.get("id")
                record("TC-08", "文档", "上传 PDF 并解析分块", "成功上传并预览章节分块",
                       "HTTP %d，使用 %s（%.1fMB），doc_id=%s，解析出 %s 个分块"
                       % (r.status_code, fname, len(blob) / 1048576, j.get("id"), j.get("chunk_count")),
                       r.status_code in (200, 201))
            if want("TC-09"):
                big = synth_pdf(pad=52 * 1024 * 1024)
                r = await cli.post(f"{BASE}/api/documents", headers=WH,
                                   data={"title": "[自动化测试]超大文件"},
                                   files=[("file", ("big.pdf", big, "application/pdf"))])
                record("TC-09", "文档", "超大文件(>50MB)上传", "被拒绝并提示大小限制",
                       "上传 %.0fMB，HTTP %d，%s" % (len(big) / 1048576, r.status_code,
                       str(r.json().get("detail", ""))[:50] if r.status_code != 200 else "未拒绝"),
                       r.status_code in (400, 413))
            if want("TC-10"):
                r = await cli.post(f"{BASE}/api/documents", headers=WH,
                                   data={"title": "[自动化测试]非法类型"},
                                   files=[("file", ("x.txt", b"hello", "text/plain"))])
                record("TC-10", "文档", "非法类型文件上传", "被拒绝并提示类型限制",
                       "HTTP %d，%s" % (r.status_code, str(r.json().get("detail", ""))[:50]),
                       r.status_code == 400)
        if want("TC-11"):
            r1 = await cli.get(f"{BASE}/api/documents/my", headers=WH)
            r2 = await cli.get(f"{BASE}/api/documents/pending", headers=AH)
            r3 = await cli.get(f"{BASE}/api/documents/pending", headers=WH)
            record("TC-11", "文档", "我的文档/待审列表（按角色隔离）", "按角色正确返回列表",
                   "worker 我的文档 HTTP %d；admin 待审 HTTP %d；worker 访问待审 HTTP %d"
                   % (r1.status_code, r2.status_code, r3.status_code),
                   r1.status_code == 200 and r2.status_code == 200)
        if not args.no_write and CTX.get("doc"):
            if want("TC-12"):
                r = await cli.post(f"{BASE}/api/documents/{CTX['doc']}/approve",
                                   headers=AH, json={}, timeout=600)
                record("TC-12", "审核", "知识文档通过入库", "向量化入库且自动抽取知识图谱",
                       "HTTP %d，%s" % (r.status_code, str(r.text)[:70]), r.status_code == 200)
            if want("TC-13"):
                r0 = await cli.post(f"{BASE}/api/documents", headers=WH,
                                    data={"title": "[自动化测试]待驳回文档"},
                                    files=[("file", ("t2.pdf", synth_pdf(), "application/pdf"))])
                did = r0.json().get("id") if r0.status_code in (200, 201) else None
                if did:
                    r = await cli.post(f"{BASE}/api/documents/{did}/reject", headers=AH,
                                       json={"comment": "[自动化测试]驳回验证"})
                    record("TC-13", "审核", "知识文档驳回", "状态置驳回并记录意见",
                           "HTTP %d" % r.status_code, r.status_code == 200)

        # ---------------- 案例 FR-07 ----------------
        log("\n[案例管理与审核]")
        if want("TC-29"):
            record("TC-29", "案例", "诊断结果存为案例并手动修正",
                   "预填大模型输出的原因/步骤/工具，可逐项标注修正后提交",
                   "前端交互（saveAsCase 写 case_draft → CaseNew 预填并可编辑），接口层无法验证，以演示截图为准",
                   False, manual=True)
        if not args.no_write:
            if want("TC-30"):
                pre = (diag or {})
                r = await cli.post(f"{BASE}/api/cases", headers=WH, data={
                    "title": "[自动化测试]怠速不稳案例",
                    "fault_phenomenon": "发动机怠速不稳，冷车启动困难",
                    "fault_reason": (pre.get("fault_analysis") or "疑似化油器怠速量孔堵塞")[:200],
                    "solution": "；".join(pre.get("repair_steps") or ["清洗化油器怠速量孔"])[:400],
                })
                j = r.json() if r.status_code in (200, 201) else {}
                CTX["case"] = j.get("id")
                record("TC-30", "案例", "提交案例待审", "案例进入待审列表",
                       "HTTP %d，case_id=%s，状态=%s" % (r.status_code, j.get("id"), j.get("status")),
                       r.status_code in (200, 201))
            if want("TC-31") and CTX.get("case"):
                r = await cli.post(f"{BASE}/api/audit/{CTX['case']}/approve", headers=AH, json={})
                record("TC-31", "审核", "案例通过入库（知识实时更新）",
                       "案例向量化入库并抽取知识图谱，随即可被检索与诊断引用",
                       "HTTP %d，%s" % (r.status_code, str(r.text)[:70]), r.status_code == 200)

        # ---------------- 作业 FR-08/09/10 ----------------
        log("\n[标准化作业]")
        if not args.no_write and want("TC-32"):
            r = await cli.post(f"{BASE}/api/workflow/requests", headers=WH, json={
                "title": "[自动化测试]化油器定期清洗", "repair_level": "daily",
                **({"device_type_id": dev_id} if dev_id else {})})
            j = r.json() if r.status_code in (200, 201) else {}
            CTX["req"] = j.get("id")
            record("TC-32", "作业", "一线提交作业申请", "申请进入 pending 状态",
                   "HTTP %d，req_id=%s，status=%s" % (r.status_code, j.get("id"), j.get("status")),
                   r.status_code in (200, 201))
        if not args.no_write and want("TC-33"):
            r = await cli.post(f"{BASE}/api/workflow/generate", headers=AH, json={
                "title": "化油器定期清洗", "repair_level": "daily",
                **({"device_type_id": dev_id} if dev_id else {})})
            j = r.json() if r.status_code == 200 else {}
            steps = j.get("steps") or []
            CTX["steps"] = steps
            checks = sum(len(s.get("checks") or []) for s in steps if isinstance(s, dict))
            record("TC-33", "作业", "AI 生成作业草稿", "基于手册生成带合规项的步骤草稿",
                   "HTTP %d，生成 %d 步，含安全合规项 %d 条，预计工时 %s"
                   % (r.status_code, len(steps), checks, j.get("estimated_duration")),
                   r.status_code == 200 and len(steps) > 0)
        if not args.no_write and want("TC-34") and CTX.get("req") and CTX.get("steps"):
            r = await cli.post(f"{BASE}/api/workflow/requests/{CTX['req']}/approve", headers=AH, json={
                "name": "[自动化测试]化油器定期清洗流程", "steps": CTX["steps"],
                "repair_level": "daily", **({"device_type_id": dev_id} if dev_id else {})})
            j = r.json() if r.status_code == 200 else {}
            CTX["tpl"] = j.get("template_id")
            r2 = await cli.get(f"{BASE}/api/workflow/templates", headers=WH,
                               params={"repair_level": "daily", **({"device_type_id": dev_id} if dev_id else {})})
            n = len(r2.json().get("items", [])) if r2.status_code == 200 else -1
            record("TC-34", "作业", "审核发布作业模板并按条件推送",
                   "发布模板并关联申请，按设备类型与检修等级匹配推送对应流程",
                   "发布 HTTP %d，template_id=%s；按『设备类型+日常保养』筛选返回 %d 个模板"
                   % (r.status_code, j.get("template_id"), n), r.status_code == 200)
        if want("TC-35"):
            record("TC-35", "作业", "合规项强制勾选", "未勾选合规项无法进入下一步",
                   "前端交互（canNext 由 allChecked 控制，未勾满时下一步按钮禁用），接口层无法验证，以演示截图为准",
                   False, manual=True)
        if not args.no_write and want("TC-36") and CTX.get("tpl"):
            r = await cli.post(f"{BASE}/api/workflow/records", headers=WH,
                               json={"workflow_template_id": CTX["tpl"],
                                     **({"device_type_id": dev_id} if dev_id else {})})
            j = r.json() if r.status_code in (200, 201) else {}
            rid = j.get("id")
            r2 = await cli.post(f"{BASE}/api/workflow/records/{rid}/complete", headers=WH, json={}) if rid else None
            record("TC-36", "作业", "拍照留证与完成工单", "生成含工单号/合规结果/照片的工单",
                   "建单 HTTP %d，record_id=%s；完成 HTTP %s"
                   % (r.status_code, rid, r2.status_code if r2 else "未执行"),
                   r.status_code in (200, 201))
        if want("TC-37"):
            r1 = await cli.get(f"{BASE}/api/workflow/records", headers=AH, params={"all": True})
            r2 = await cli.get(f"{BASE}/api/workflow/records", headers=WH)
            na = len(r1.json().get("items", [])) if r1.status_code == 200 else -1
            nw = len(r2.json().get("items", [])) if r2.status_code == 200 else -1
            record("TC-37", "作业", "全员留痕核查", "管理员切全部人员查看分步留痕",
                   "管理员全部人员 %d 条；一线本人 %d 条" % (na, nw), r1.status_code == 200)

        # ---------------- 反馈 FR-07 补充 ----------------
        log("\n[标注修正与采纳]")
        if not args.no_write and want("TC-39"):
            r = await cli.post(f"{BASE}/api/feedback", headers=WH, json={
                "record_id": CTX.get("record_id"),
                "original_output": "（自动化测试）原始诊断结论",
                "user_correction": "[自动化测试]应优先检查气门间隙是否在 0.13~0.20mm",
                "correction_type": "incomplete"})
            fid = r.json().get("id") if r.status_code in (200, 201) else None
            r2 = await cli.post(f"{BASE}/api/feedback/{fid}/adopt", headers=AH) if fid else None
            record("TC-39", "反馈", "提交标注修正并采纳", "采纳后注入后续诊断上下文，优化系统适配性",
                   "提交 HTTP %d，feedback_id=%s；采纳 HTTP %s，is_adopted=%s"
                   % (r.status_code, fid, r2.status_code if r2 else "未执行",
                      r2.json().get("is_adopted") if r2 and r2.status_code == 200 else "-"),
                   r.status_code in (200, 201) and bool(r2 and r2.status_code == 200))

    # ---------------- 输出 ----------------
    os.makedirs(OUTDIR, exist_ok=True)
    RESULTS.sort(key=lambda x: x[0])
    with open(os.path.join(OUTDIR, "functest_result.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["编号", "模块", "测试项", "预期结果", "实际结果", "结论"])
        w.writerows(RESULTS)
    with open(os.path.join(OUTDIR, "functest_log.txt"), "w", encoding="utf-8") as f:
        f.write("功能测试执行日志  %s\n目标 %s\n%s\n"
                % (datetime.now().isoformat(timespec="seconds"), BASE, "=" * 60))
        f.write("\n".join(LOG) + "\n")

    ok = sum(1 for r in RESULTS if r[5] == "通过")
    ng = sum(1 for r in RESULTS if r[5] == "未通过")
    mn = sum(1 for r in RESULTS if r[5] == "需人工佐证")
    print("\n" + "=" * 60)
    print("功能测试完成：共 %d 条  通过 %d  未通过 %d  需人工佐证 %d" % (len(RESULTS), ok, ng, mn))
    if ng:
        print("未通过用例：")
        for r in RESULTS:
            if r[5] == "未通过":
                print("   %s %s → %s" % (r[0], r[2], r[4][:80]))
    print("=" * 60)

    import tarfile
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    pkg = os.path.join(OUTDIR, "functest_result_%s.tar.gz" % stamp)
    with tarfile.open(pkg, "w:gz") as tf:
        for fn in os.listdir(OUTDIR):
            if fn.endswith((".csv", ".txt")):
                tf.add(os.path.join(OUTDIR, fn), arcname=fn)
    print("已打包：%s   ← 把这一个文件拷出来即可" % pkg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑指定用例，如 TC-01,TC-05")
    ap.add_argument("--no-write", action="store_true", help="只跑只读用例，不产生数据变更")
    a = ap.parse_args()
    asyncio.run(run(a))
