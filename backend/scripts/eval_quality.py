#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检索与诊断质量评测脚本 —— 支撑《软件功能测试报告》3.3 节的三个指标：
  · 知识检索 Top-3 命中率
  · 诊断结论 [来源N] 溯源标注正确率
  · 分步检修指引平均收敛步数

用法：
    1) 先填评测集：python3 scripts/eval_quality.py --init      # 生成 evalset.csv 模板
       在 evalset.csv 里补齐每条 query 的「期望命中关键词」（手册中该答案必然出现的词，
       用 | 分隔任一命中即算，如：气门间隙|0.05|0.10）
    2) 跑评测：      python3 scripts/eval_quality.py --run
    3) 人工复核：    打开 eval_out/retrieval_detail.csv，逐条确认自动判定是否正确，
                    如需修正把「人工判定」列改成 1/0，再执行 --recount 重算

产出（eval_out/）：
    retrieval_detail.csv   每条查询的 Top-3 返回、自动命中判定、人工判定列
    citation_detail.csv    每条诊断的 [来源N] 标注与 sources 对照
    guide_detail.csv       每次分步指引的收敛步数
    quality_report.txt     三个指标的最终数值（填入报告 3.3 节）
"""
import argparse, asyncio, csv, os, re, statistics, sys
from datetime import datetime

try:
    import httpx
except ImportError:
    sys.exit("缺少依赖：pip install httpx --break-system-packages")

BASE     = os.environ.get("BENCH_BASE", "http://127.0.0.1:8000")
USERNAME = os.environ.get("BENCH_USER", "worker")
PASSWORD = os.environ.get("BENCH_PASS", "worker123")
OUTDIR   = os.environ.get("EVAL_OUT", "eval_out")
EVALSET  = os.environ.get("EVAL_SET", "evalset.csv")

# 模板：50 条中先给出 12 条示例，其余请按同样格式补齐到 50 条
TEMPLATE = [
    ("检索", "气门间隙的标准值是多少", "气门间隙"),
    ("检索", "机油应该多久更换一次", "机油|更换"),
    ("检索", "火花塞的电极间隙标准", "火花塞|间隙"),
    ("检索", "化油器怠速如何调整", "化油器|怠速"),
    ("检索", "气缸压缩压力的正常范围", "压缩压力|气缸"),
    ("检索", "正时链条的张紧度检查方法", "正时|链条"),
    ("检索", "离合器打滑怎么检查", "离合器"),
    ("检索", "曲轴箱通气系统的作用", "曲轴箱"),
    ("诊断", "发动机怠速不稳，冷车启动困难", ""),
    ("诊断", "加速无力，排气冒蓝烟", ""),
    ("诊断", "发动机异响，转速升高时加剧", ""),
    ("诊断", "水温偏高，风扇运转正常", ""),
]


def init_set():
    if os.path.exists(EVALSET):
        sys.exit("%s 已存在，避免覆盖，请先备份或删除" % EVALSET)
    with open(EVALSET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["类型", "查询/故障描述", "期望命中关键词(|分隔)"])
        w.writerows(TEMPLATE)
    print("已生成 %s（%d 条示例）。请补齐到 50 条后执行 --run" % (EVALSET, len(TEMPLATE)))
    print("说明：类型填「检索」或「诊断」；检索条目必须填期望命中关键词，诊断条目可留空。")


def load_set():
    if not os.path.exists(EVALSET):
        sys.exit("找不到 %s，请先执行 --init" % EVALSET)
    rows = []
    with open(EVALSET, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            q = (r.get("查询/故障描述") or "").strip()
            if q:
                rows.append((r.get("类型", "").strip(), q, (r.get("期望命中关键词(|分隔)") or "").strip()))
    return rows


_WS = re.compile(r"\s+")
_TRANS = str.maketrans({"～": "~", "－": "-", "（": "(", "）": ")",
                        "：": ":", "，": ",", "×": "x", "·": "."})


def norm(t: str) -> str:
    """归一化：去掉全部空白 + 统一全半角。
    手册 PDF 抽取出来的空格很不规整——同一份手册里既有『12 ± 1.5』也有『12±1.5』，
    直接做子串匹配会产生大量假阴性，因此两边都先归一化再比。"""
    return _WS.sub("", (t or "")).translate(_TRANS).lower()


def hit_any(keywords: str, text: str) -> bool:
    nt = norm(text)
    return any(k.strip() and norm(k) in nt for k in keywords.split("|"))


async def login(cli):
    r = await cli.post(f"{BASE}/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


async def run(args):
    rows = load_set()
    ret = [r for r in rows if r[0] == "检索"]
    dia = [r for r in rows if r[0] == "诊断"]
    os.makedirs(OUTDIR, exist_ok=True)
    rdet, cdet, gdet = [], [], []

    async with httpx.AsyncClient(trust_env=False, timeout=300) as cli:
        hdr = {"Authorization": "Bearer " + await login(cli)}

        # ---- 1. 检索 Top-3 命中率 ----
        print("[检索评测] %d 条" % len(ret))
        for i, (_, q, kws) in enumerate(ret, 1):
            try:
                r = await cli.post(f"{BASE}/api/knowledge/search", headers=hdr,
                                   data={"query": q, "top_k": 3})
                st = r.status_code
                j = r.json() if st == 200 else {}
                items = j.get("results") or j.get("items") or []
            except Exception as e:
                rdet.append([i, q, kws, "ERR", "请求异常: %s" % str(e)[:60], 0, ""]); continue
            texts = " ".join((it.get("title", "") + it.get("content", "")) for it in items[:3])
            hit = int(hit_any(kws, texts)) if kws else ""
            if st != 200:
                titles = "HTTP %d: %s" % (st, r.text[:80])
            elif not items:
                titles = "（接口 200 但返回 0 条）"
            else:
                titles = " / ".join((it.get("title") or "")[:24] for it in items[:3])
            rdet.append([i, q, kws, st, titles, hit, ""])
            print("  %2d/%d [HTTP %s] %s → %s" % (i, len(ret), st, q[:18],
                  "命中" if hit else ("返回空" if st == 200 and not items else "未命中")))

        # ---- 2. 诊断溯源标注正确率 + 3. 分步指引收敛步数 ----
        print("[诊断评测] %d 条" % len(dia))
        for i, (_, q, _) in enumerate(dia, 1):
            try:
                r = await cli.post(f"{BASE}/api/diagnosis/analyze", headers=hdr,
                                   data={"description": q})
                j = r.json()
            except Exception as e:
                cdet.append([i, q, "ERR", "请求异常: %s" % str(e)[:60], "", 0, ""]); continue
            answer = j.get("answer", "") or ""
            marks  = sorted(set(int(m) for m in re.findall(r"\[来源(\d+)\]", answer)))
            srcs   = j.get("sources") or []
            valid  = [m for m in marks if 1 <= m <= len(srcs)]
            # 自动判定：所有 [来源N] 都指向真实存在的参考资料，且至少标注了一条
            ok = int(bool(marks) and len(valid) == len(marks))
            cdet.append([i, q, "|".join(map(str, marks)), len(srcs),
                         "|".join(map(str, valid)), ok, ""])
            print("  %2d/%d %s → 标注 %s / 资料 %d 条 → %s"
                  % (i, len(dia), q[:18], marks or "无", len(srcs), "正确" if ok else "存疑"))

            if not args.skip_guide:
                # 反馈策略：模拟真实现场——第 2 步反馈"异常"给出线索，其余"正常"。
                # 若一律回答"正常"，模型永远无法定位根因，必然打满 MAX_STEPS，
                # 那测出来的是护栏上限而不是真实收敛步数。
                hist, steps, final = [], 0, False
                for k in range(8):
                    g = await cli.post(f"{BASE}/api/diagnosis/guide/step", headers=hdr,
                                       json={"fault_description": q, "history": hist})
                    gj = g.json(); steps += 1
                    if gj.get("is_final"):
                        final = True; break
                    # /guide/step 直接返回 step 对象本身，字段平铺，没有外层 "step" 包装。
                    # 之前误写成 gj.get("step") 导致 action 恒为空串，模型收不到有效历史，
                    # 每次都打满 MAX_STEPS —— 上一轮「平均 8 步」就是这么来的。
                    res = "异常" if k == 1 else "正常"
                    hist.append({"action": gj.get("action", ""), "result": res,
                                 "note": "该项检查发现异常" if res == "异常" else ""})
                gdet.append([i, q, steps, "是" if final else "否(达步数上限)",
                             "第2步反馈异常，其余正常"])
                print("       分步指引：%d 步%s" % (steps, "定论" if final else "未定论(达上限)"))

    _write("retrieval_detail.csv", ["序号", "查询", "期望关键词", "HTTP", "Top-3 返回标题", "自动判定(1命中)", "人工判定(留空=采用自动)"], rdet)
    _write("citation_detail.csv", ["序号", "故障描述", "[来源N]标注", "sources条数", "有效标注", "自动判定(1正确)", "人工判定(留空=采用自动)"], cdet)
    if gdet:
        _write("guide_detail.csv", ["序号", "故障描述", "收敛步数", "是否定论", "反馈策略"], gdet)
    recount()


def _write(name, header, rows):
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, name), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print("  写出 %s/%s" % (OUTDIR, name))


def _judge(path, auto_col, manual_col):
    fp = os.path.join(OUTDIR, path)
    if not os.path.exists(fp):
        return []
    out = []
    with open(fp, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            man = (r.get(manual_col) or "").strip()
            val = man if man in ("0", "1") else (r.get(auto_col) or "").strip()
            if val in ("0", "1"):
                out.append(int(val))
    return out


def recount():
    """按 CSV 中的判定列（人工优先）重算三个指标。"""
    hits = _judge("retrieval_detail.csv", "自动判定(1命中)", "人工判定(留空=采用自动)")
    cits = _judge("citation_detail.csv", "自动判定(1正确)", "人工判定(留空=采用自动)")
    steps = []
    fp = os.path.join(OUTDIR, "guide_detail.csv")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                try: steps.append(int(r["收敛步数"]))
                except Exception: pass

    L = ["=" * 60,
         "检索与诊断质量评测结果   %s" % datetime.now().isoformat(timespec="seconds"),
         "评测集：%s   目标：%s" % (EVALSET, BASE), "=" * 60]
    if hits:
        L.append("知识检索 Top-3 命中率：%d/%d = %.1f%%" % (sum(hits), len(hits), sum(hits) / len(hits) * 100))
    if cits:
        L.append("诊断 [来源N] 溯源标注正确率：%d/%d = %.1f%%" % (sum(cits), len(cits), sum(cits) / len(cits) * 100))
    if steps:
        L.append("分步检修指引平均收敛步数：%.1f 步（%d 次，最少 %d 步，最多 %d 步）"
                 % (statistics.mean(steps), len(steps), min(steps), max(steps)))
    L.append("")
    L.append("注：以上为自动判定结果。请打开 %s/ 下的明细 CSV 逐条复核，" % OUTDIR)
    L.append("    在「人工判定」列填 1/0 修正后执行 --recount 重算，明细 CSV 作为测试报告附录提交。")
    txt = "\n".join(L)
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "quality_report.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print("\n" + txt)

    # 打包，便于从 V11 虚拟机下载
    import tarfile
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    pkg = os.path.join(OUTDIR, "quality_result_%s.tar.gz" % stamp)
    with tarfile.open(pkg, "w:gz") as tf:
        for fn in os.listdir(OUTDIR):
            if fn.endswith((".csv", ".txt")):
                tf.add(os.path.join(OUTDIR, fn), arcname=fn)
        if os.path.exists(EVALSET):
            tf.add(EVALSET, arcname=os.path.basename(EVALSET))
    print("\n已打包：%s   ← 把这一个文件从虚拟机拷出来即可" % pkg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="生成评测集模板")
    ap.add_argument("--run", action="store_true", help="执行评测")
    ap.add_argument("--recount", action="store_true", help="按人工判定重算指标")
    ap.add_argument("--skip-guide", action="store_true", help="跳过分步指引（较慢）")
    a = ap.parse_args()
    if a.init: init_set()
    elif a.run: asyncio.run(run(a))
    elif a.recount: recount()
    else: ap.print_help()
