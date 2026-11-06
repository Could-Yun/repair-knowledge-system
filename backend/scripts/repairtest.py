#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「排查定论 → 现场维修作业」功能测试脚本
用于产出《软件功能测试报告》中新增接口 POST /api/diagnosis/repair-plan 的实测数据。

与 benchmark.py 的分工：benchmark.py 测的是「故障诊断」环节的耗时，
本脚本测的是诊断定论之后「生成维修作业方案」这一新增环节，两者不可混为一谈。

用法（venv 已激活、服务已启动）：
    python3 repairtest.py                     # 云端通道，5 个故障场景 × 3 轮 = 15 次
    python3 repairtest.py --rounds 2          # 每个场景 2 轮
    python3 repairtest.py --local             # 强制走本地兜底模型（断网场景）
    python3 repairtest.py --out repair_out    # 指定输出目录

产出：
    repair_raw.csv      每次调用的原始记录（附录用，逐行可核）
    repair_summary.csv  汇总指标（填表用）
    repair_report.txt   汇总文本，可直接抄进测试报告
"""
import argparse, csv, json, os, statistics, sys, time
from datetime import datetime

try:
    import httpx
except ImportError:
    sys.exit("缺少依赖：pip install httpx --break-system-packages")

BASE     = os.environ.get("RP_BASE", "http://127.0.0.1:8000")
USERNAME = os.environ.get("RP_USER", "worker")
PASSWORD = os.environ.get("RP_PASS", "worker123")

# ------------------------------------------------------------------
# 测试场景：模拟分步排查已经收敛出的「根本原因」。
# 五条根本原因全部取自内置《摩托车发动机维修手册》覆盖的故障域，
# 便于核验模型是否真的引用了手册中的规格数值（而不是自由发挥）。
# ------------------------------------------------------------------
CASES = [
    {
        "name": "气门间隙超差",
        "fault": "摩托车发动机怠速抖动、动力下降，冷车启动后气缸头部位有规律的哒哒金属敲击声，热车后略减轻",
        "cause": "根本原因为气门间隙严重超差，进气门实测 0.15mm、排气门实测 0.22mm，均超出标准值上限，"
                 "导致冷车时气门落座冲击加剧产生哒哒声；热车后金属膨胀使间隙缩小、冲击减弱但配气相位仍失准，"
                 "故动力持续下降。处置方案：按标准值重新调整进排气门间隙并更换磨损的调整垫片。",
        "history": [
            {"action": "检查气门间隙（冷车状态下用塞尺测量进排气门）", "result": "异常", "note": "进气门0.15mm，排气门0.22mm"},
            {"action": "检查火花塞积碳与电极间隙", "result": "正常", "note": ""},
        ],
    },
    {
        "name": "凸轮轴磨损",
        "fault": "发动机高转速时异响明显，动力下降，机油中发现细微金属屑",
        "cause": "根本原因为凸轮轴桃尖异常磨损及轴承座锈蚀，导致气门升程不足、配气相位失准，"
                 "金属屑来自凸轮轴与挺柱的干摩擦。处置方案：更换凸轮轴总成及配套滑动挺柱，清洁气缸头油道。",
        "history": [
            {"action": "拆下气缸头盖检查凸轮轴桃尖磨损情况", "result": "异常", "note": "桃尖可见明显偏磨"},
            {"action": "检查机油滤网是否有金属屑", "result": "异常", "note": "滤网附着细微金属屑"},
        ],
    },
    {
        "name": "化油器堵塞",
        "fault": "发动机怠速不稳容易熄火，加速时明显迟滞，冷车启动困难",
        "cause": "根本原因为化油器主量孔与怠速量孔被胶质沉积物堵塞，混合气过稀导致怠速不稳与加速迟滞。"
                 "处置方案：拆解化油器彻底清洗量孔与浮子室，更换密封件后按标准重新调整怠速与混合比。",
        "history": [
            {"action": "检查空气滤清器是否堵塞", "result": "正常", "note": ""},
            {"action": "拆检化油器浮子室与量孔", "result": "异常", "note": "量孔可见胶质沉积"},
        ],
    },
    {
        "name": "活塞环磨损",
        "fault": "排气冒蓝烟，机油消耗量异常增大，动力明显不足",
        "cause": "根本原因为活塞环磨损失去弹性、开口间隙超标，机油窜入燃烧室参与燃烧形成蓝烟，"
                 "同时气缸压缩压力下降导致动力不足。处置方案：更换活塞环组，检测气缸磨损量并按需镗缸配活塞。",
        "history": [
            {"action": "检测气缸压缩压力", "result": "异常", "note": "低于标准值约30%"},
            {"action": "检查气门油封是否老化", "result": "正常", "note": ""},
        ],
    },
    {
        "name": "冷却系统失效",
        "fault": "发动机温度过高，长时间行驶后有明显异味，冷却风扇工作正常",
        "cause": "根本原因为冷却液长期未更换导致水道结垢、循环受阻，散热器散热效率大幅下降，"
                 "叠加节温器开启滞后，形成局部过热。处置方案：清洗水道并更换冷却液，同时更换节温器与老化的水管密封件。",
        "history": [
            {"action": "检查冷却液液位与颜色", "result": "异常", "note": "液位偏低且浑浊"},
            {"action": "检查冷却风扇是否正常启停", "result": "正常", "note": ""},
        ],
    },
]

# 用于核验方案是否落到手册规格上的关键词（出现任一即视为「含具体规格」）
SPEC_HINTS = ["mm", "N·m", "Nm", "牛米", "标准值", "扭矩", "间隙", "公差", "规格", "MPa", "kPa", "℃", "转/分", "r/min"]


def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s))) - 1))
    return s[k]


def login(client):
    r = client.post(f"{BASE}/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    r.raise_for_status()
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def device_id(client, headers):
    """取「摩托车发动机」设备类型 id，取不到就传 None（不影响接口可用性）"""
    try:
        r = client.get(f"{BASE}/api/devices", headers=headers, params={"page": 1, "size": 100})
        for d in r.json().get("items", []):
            if "摩托" in d.get("name", "") or "发动机" in d.get("name", ""):
                return d["id"]
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3, help="每个故障场景重复次数，默认 3")
    ap.add_argument("--local", action="store_true", help="强制本地兜底模型（模拟断网）")
    ap.add_argument("--out", default="repair_out", help="输出目录")
    ap.add_argument("--timeout", type=float, default=900, help="单次请求超时秒数，本地模型需放宽")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    channel = "LOCAL(本地兜底)" if args.local else "CLOUD(云端 qwen-plus)"

    print("=" * 62)
    print(" 维修方案生成（POST /api/diagnosis/repair-plan）功能与性能测试")
    print(f" 通道: {channel}   场景: {len(CASES)}   每场景轮次: {args.rounds}")
    print(f" 服务: {BASE}   超时: {args.timeout:.0f}s")
    print("=" * 62)

    if args.local:
        print("\n提示：--local 依赖后端支持强制本地通道。若后端未提供该开关，")
        print("      请改为在 .env 中把 CHAT_BASE_URL 指向本地 llama-server 后重启后端再跑。\n")

    rows = []
    with httpx.Client(timeout=args.timeout) as client:
        headers = login(client)
        dev = device_id(client, headers)
        print(f"登录成功，设备类型 id = {dev or '（未匹配到，按通用处理）'}\n")

        n = 0
        for rd in range(1, args.rounds + 1):
            for c in CASES:
                n += 1
                payload = {
                    "record_id": None,
                    "device_type_id": dev,
                    "fault_description": c["fault"],
                    "root_cause": c["cause"],
                    "history": c["history"],
                }
                if args.local:
                    payload["force_local"] = True   # 后端若不识别该字段会被忽略，不影响调用

                t0 = time.time()
                ok, err, steps, checks, tools, risks, specs, title, dur = 0, "", 0, 0, 0, 0, 0, "", None
                try:
                    r = client.post(f"{BASE}/api/diagnosis/repair-plan", headers=headers, json=payload)
                    el = time.time() - t0
                    if r.status_code == 200:
                        data = r.json()
                        st = data.get("steps") or []
                        steps = len(st)
                        title = (data.get("plan_title") or "")[:60]
                        dur = data.get("estimated_duration")
                        checks = sum(len(s.get("checks") or []) for s in st)
                        tools = sum(len(s.get("tools") or []) for s in st)
                        risks = sum(1 for s in st if (s.get("risk") or "").strip())
                        blob = json.dumps(st, ensure_ascii=False)
                        specs = sum(1 for h in SPEC_HINTS if h in blob)
                        ok = 1 if steps > 0 else 0
                        if not ok:
                            err = "返回步骤为空"
                    else:
                        err = f"HTTP {r.status_code}: {r.text[:120]}"
                except Exception as e:
                    el = time.time() - t0
                    err = f"{type(e).__name__}: {e}"[:140]

                rows.append({
                    "序号": n, "轮次": rd, "故障场景": c["name"], "通道": channel,
                    "耗时(s)": round(el, 2), "是否成功": ok,
                    "步骤数": steps, "确认项总数": checks, "工具项总数": tools,
                    "含风险提示步数": risks, "命中规格关键词种类": specs,
                    "预计工时(min)": dur if dur is not None else "",
                    "方案名称": title, "错误信息": err,
                    "时间戳": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                flag = "OK " if ok else "FAIL"
                print(f"[{n:>3}] {flag} {c['name']:<8} {el:>7.2f}s  步骤{steps:>2}  确认{checks:>3}  "
                      f"规格词{specs:>2}  {title[:24]}{'  ' + err if err else ''}")

    # ---------------- 汇总 ----------------
    raw = os.path.join(args.out, "repair_raw.csv")
    with open(raw, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    okr = [r for r in rows if r["是否成功"] == 1]
    lat = [r["耗时(s)"] for r in okr]
    summary = {
        "样本总数": len(rows),
        "成功数": len(okr),
        "成功率(%)": round(100 * len(okr) / len(rows), 1) if rows else 0,
        "平均耗时(s)": round(statistics.mean(lat), 2) if lat else 0,
        "中位耗时(s)": round(statistics.median(lat), 2) if lat else 0,
        "P95耗时(s)": round(pct(lat, 95), 2) if lat else 0,
        "最大耗时(s)": round(max(lat), 2) if lat else 0,
        "最小耗时(s)": round(min(lat), 2) if lat else 0,
        "平均步骤数": round(statistics.mean([r["步骤数"] for r in okr]), 1) if okr else 0,
        "平均确认项数": round(statistics.mean([r["确认项总数"] for r in okr]), 1) if okr else 0,
        "平均工具项数": round(statistics.mean([r["工具项总数"] for r in okr]), 1) if okr else 0,
        "含风险提示步骤占比(%)": round(100 * sum(r["含风险提示步数"] for r in okr) /
                                     max(1, sum(r["步骤数"] for r in okr)), 1) if okr else 0,
        "方案含具体规格数值的比例(%)": round(100 * sum(1 for r in okr if r["命中规格关键词种类"] >= 2) /
                                          max(1, len(okr)), 1) if okr else 0,
        "通道": channel,
    }
    with open(os.path.join(args.out, "repair_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["指标", "数值"])
        for k, v in summary.items():
            w.writerow([k, v])

    lines = ["=" * 62, " 维修方案生成 测试汇总", "=" * 62]
    for k, v in summary.items():
        lines.append(f"  {k:<24}{v}")
    lines.append("")
    lines.append("  分场景平均耗时：")
    for c in CASES:
        xs = [r["耗时(s)"] for r in okr if r["故障场景"] == c["name"]]
        lines.append(f"    {c['name']:<10}{'%.2f' % statistics.mean(xs) if xs else '—':>8} s   "
                     f"（成功 {len(xs)}/{args.rounds}）")
    fails = [r for r in rows if r["是否成功"] == 0]
    if fails:
        lines.append("")
        lines.append("  失败样本：")
        for r in fails:
            lines.append(f"    #{r['序号']} {r['故障场景']}  {r['错误信息']}")
    txt = "\n".join(lines)
    with open(os.path.join(args.out, "repair_report.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")

    print("\n" + txt)
    print(f"\n原始样本：{raw}")
    print(f"汇总：    {os.path.join(args.out, 'repair_summary.csv')}")


if __name__ == "__main__":
    main()
