#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备检修知识检索与作业系统 —— 性能测试脚本
用于产出《软件功能测试报告》第三章的实测数据，并保留原始样本作为附录。

用法（在 backend 目录、venv 激活、服务已启动的前提下）：
    # httpx 已在 requirements.txt 中，无需额外安装；资源采样读 /proc，无需 psutil
    python3 scripts/benchmark.py                        # 全量
    python3 scripts/benchmark.py --rounds 30            # 每项采样 30 次
    python3 scripts/benchmark.py --skip multimodal      # 跳过多模态（无 VL Key 时）
    python3 scripts/benchmark.py --only concurrency     # 只跑并发

产出（默认写到 backend/benchmark_out/）：
    raw_samples.csv     每一次调用的原始耗时（附录用）
    summary.csv         各项 avg / P50 / P95 / max（填表 3-1 用）
    concurrency.csv     并发测试逐请求结果
    resource.csv        内存/CPU 周期采样
    report.txt          汇总文本，可直接抄进测试报告
"""
import argparse, asyncio, csv, io, json, os, statistics, sys, time
from datetime import datetime

try:
    import httpx
except ImportError:
    sys.exit("缺少依赖：pip install httpx --break-system-packages")
# 资源采样直接读 /proc，纯 Python 零依赖 —— LoongArch 上无需编译 psutil

BASE     = os.environ.get("BENCH_BASE", "http://127.0.0.1:8000")
USERNAME = os.environ.get("BENCH_USER", "worker")
PASSWORD = os.environ.get("BENCH_PASS", "worker123")
OUTDIR   = os.environ.get("BENCH_OUT", "benchmark_out")

# 测试查询集：均围绕内置《摩托车发动机维修手册》构造
FAULT_CASES = [
    "发动机怠速不稳，冷车启动困难，排气管有异响",
    "发动机动力下降，加速无力，偶尔回火",
    "机油消耗异常增大，排气冒蓝烟",
    "发动机温度过高，冷却风扇工作正常",
    "启动后有明显金属敲击声，转速升高时加剧",
]
SEARCH_QUERIES = [
    "气门间隙的标准值是多少",
    "化油器怠速调整方法",
    "机油更换周期与规格",
    "火花塞间隙标准",
    "曲轴箱压缩压力检测步骤",
]


# ---------------------------------------------------------------- 工具
def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100 * len(s))) - 1))
    return s[k]


def stat(xs):
    if not xs:
        return dict(n=0, avg=0, p50=0, p95=0, mn=0, mx=0)
    return dict(n=len(xs), avg=statistics.mean(xs), p50=pct(xs, 50),
                p95=pct(xs, 95), mn=min(xs), mx=max(xs))


def load_test_image():
    """诊断用测试图片。
    优先读取脚本同目录下的真实现场照片（test_image.jpg / .png / .jpeg），
    找不到才回落到合成图。**正式出数据请务必放真实故障照片**——
    合成图不携带故障语义，VL 描述对诊断无贡献，那一行数据只能代表链路耗时。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("test_image.jpg", "test_image.jpeg", "test_image.png",
                 "test_image.JPG", "test_image.PNG"):
        fp = os.path.join(here, name)
        if os.path.exists(fp):
            with open(fp, "rb") as f:
                blob = f.read()
            mime = "image/png" if name.lower().endswith(".png") else "image/jpeg"
            print("[图片] 使用真实照片 %s（%.0f KB）" % (name, len(blob) / 1024))
            return blob, name, mime
    try:
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (320, 320), (60, 66, 80))
        d = ImageDraw.Draw(im)
        d.rectangle([60, 60, 260, 260], outline=(220, 180, 60), width=6)
        d.line([60, 60, 260, 260], fill=(200, 70, 70), width=5)
        buf = io.BytesIO(); im.save(buf, "PNG")
        print("[图片] ⚠ 未找到 test_image.*，回落到合成图。")
        print("       合成图只能测多模态链路耗时，不能代表真实多模态诊断，")
        print("       正式采数请把现场故障照片放到 scripts/test_image.jpg")
        return buf.getvalue(), "synthetic.png", "image/png"
    except ImportError:
        print("[图片] 未找到 test_image.* 且 PIL 不可用，将跳过多模态测试")
        return None, None, None


async def login(cli):
    r = await cli.post(f"{BASE}/api/auth/login",
                       json={"username": USERNAME, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


# ---------------------------------------------------------------- 单项计时
async def t_diagnosis(cli, hdr, desc, image=None, fname="shot.png", mime="image/png"):
    files = [("images", (fname, image, mime))] if image else None
    t0 = time.perf_counter()
    r = await cli.post(f"{BASE}/api/diagnosis/analyze", headers=hdr,
                       data={"description": desc}, files=files, timeout=900)
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return dt, r.json()


async def t_search(cli, hdr, q):
    t0 = time.perf_counter()
    r = await cli.post(f"{BASE}/api/knowledge/search", headers=hdr,
                       data={"query": q, "top_k": 3}, timeout=60)
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return dt, r.json()


async def t_guide(cli, hdr, desc, history):
    t0 = time.perf_counter()
    r = await cli.post(f"{BASE}/api/diagnosis/guide/step", headers=hdr,
                       json={"fault_description": desc, "history": history}, timeout=180)
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return dt, r.json()


# ---------------------------------------------------------------- 主流程
async def run_latency(cli, hdr, rounds, skip, raw):
    res = {}
    img, imgname, imgmime = load_test_image()

    async def loop(name, fn, n):
        print(f"  [{name}] 预热 1 次…", flush=True)
        try:
            await fn(0)
        except Exception as e:
            print(f"  [{name}] 预热失败：{e}")
        xs = []
        for i in range(n):
            try:
                dt = await fn(i)
                xs.append(dt)
                raw.append([name, i + 1, round(dt, 4), datetime.now().isoformat(timespec="seconds")])
                print(f"  [{name}] {i+1}/{n}  {dt:.2f}s", flush=True)
            except Exception as e:
                raw.append([name, i + 1, "ERROR", str(e)[:60]])
                print(f"  [{name}] {i+1}/{n}  失败 {e}", flush=True)
        res[name] = stat(xs)

    if "text" not in skip:
        await loop("文本故障诊断",
                   lambda i: _first(t_diagnosis(cli, hdr, FAULT_CASES[i % len(FAULT_CASES)])), rounds)
    if "multimodal" not in skip and img:
        await loop("多模态诊断",
                   lambda i: _first(t_diagnosis(cli, hdr, FAULT_CASES[i % len(FAULT_CASES)],
                                                img, imgname, imgmime)), rounds)
    if "search" not in skip:
        await loop("知识检索", lambda i: _first(t_search(cli, hdr, SEARCH_QUERIES[i % len(SEARCH_QUERIES)])), rounds)
    if "guide" not in skip:
        hist = [{"action": "检查火花塞积碳情况", "result": "正常", "note": ""}]
        await loop("分步指引单步", lambda i: _first(t_guide(cli, hdr, FAULT_CASES[i % len(FAULT_CASES)], hist)), rounds)
    return res


async def _first(coro):
    dt, _ = await coro
    return dt


async def run_concurrency(cli, hdr, n, out):
    print(f"\n[并发测试] {n} 路并行诊断…", flush=True)
    t0 = time.perf_counter()

    async def one(i):
        s = time.perf_counter()
        try:
            await cli.post(f"{BASE}/api/diagnosis/analyze", headers=hdr,
                           data={"description": FAULT_CASES[i % len(FAULT_CASES)]}, timeout=300)
            return i, time.perf_counter() - s, "OK"
        except Exception as e:
            return i, time.perf_counter() - s, "ERROR: %s" % str(e)[:50]

    rows = await asyncio.gather(*[one(i) for i in range(n)])
    wall = time.perf_counter() - t0
    ok = [r for r in rows if r[2] == "OK"]
    lat = [r[1] for r in ok]
    for i, dt, st in rows:
        out.append([i + 1, round(dt, 3), st])
    return dict(并发数=n, 成功=len(ok), 失败=n - len(ok),
                错误率="%.1f%%" % ((n - len(ok)) / n * 100),
                总墙钟="%.2fs" % wall, 平均="%.2fs" % (statistics.mean(lat) if lat else 0),
                P95="%.2fs" % pct(lat, 95), 吞吐="%.2f req/s" % (len(ok) / wall if wall else 0))


def _find_backend_pids():
    """扫描 /proc 找出后端进程（uvicorn / app.main / gunicorn）。"""
    pids = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % d, "rb") as f:
                cmd = f.read().decode("utf-8", "ignore")
        except Exception:
            continue
        if ("uvicorn" in cmd or "app.main" in cmd or "gunicorn" in cmd) and "benchmark.py" not in cmd:
            pids.append(int(d))
    return pids


def _rss_mb(pid):
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


def _cpu_ticks(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            parts = f.read().rsplit(") ", 1)[-1].split()
        return int(parts[11]) + int(parts[12])       # utime + stime
    except Exception:
        return 0


def _sysmem_mb():
    """返回 (已用MB, 总量MB)。"""
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) / 1024.0
    except Exception:
        return 0.0, 0.0
    total = info.get("MemTotal", 0.0)
    avail = info.get("MemAvailable", info.get("MemFree", 0.0))
    return total - avail, total


def sample_resource(stop, out, interval=1.0):
    """后台线程：周期采样后端进程内存/CPU 与系统内存（纯 /proc 实现）。"""
    if not os.path.isdir("/proc"):
        print("[WARN] 非 Linux 环境，跳过资源采样")
        return
    pids = _find_backend_pids()
    if not pids:
        print("[WARN] 未找到 uvicorn/gunicorn 进程，资源采样跳过")
        print("       可手工记录：watch -n1 'ps -o rss=,pcpu= -p <后端PID>'")
        return
    print("[资源采样] 监控进程 PID: %s，每 %.0f 秒一次" % (pids, interval))
    hz = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    last = {p: _cpu_ticks(p) for p in pids}
    last_t = time.time()
    while not stop.is_set():
        stop.wait(interval)
        now_t = time.time()
        dt = max(1e-6, now_t - last_t)
        rss = cpu = 0.0
        for p in list(pids):
            rss += _rss_mb(p)
            cur = _cpu_ticks(p)
            cpu += (cur - last.get(p, cur)) / hz / dt * 100.0
            last[p] = cur
        last_t = now_t
        used, total = _sysmem_mb()
        out.append([datetime.now().isoformat(timespec="seconds"), round(rss, 1),
                    round(cpu, 1), round(used, 1),
                    round(used / total * 100, 1) if total else 0.0])


def write(path, header, rows):
    os.makedirs(OUTDIR, exist_ok=True)
    fp = os.path.join(OUTDIR, path)
    with open(fp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print("  写出", fp)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=20, help="每项采样次数（≥20）")
    ap.add_argument("--concurrency", type=int, default=20, help="并发路数")
    ap.add_argument("--skip", default="", help="跳过项：text,multimodal,search,guide,concurrency")
    ap.add_argument("--only", default="", help="只跑某项")
    args = ap.parse_args()
    skip = set(x.strip() for x in args.skip.split(",") if x.strip())
    if args.only:
        skip = {"text", "multimodal", "search", "guide", "concurrency"} - {args.only}

    import threading
    raw, conc_rows, res_rows = [], [], []
    stop = threading.Event()
    th = threading.Thread(target=sample_resource, args=(stop, res_rows), daemon=True)
    th.start()

    print("=" * 66)
    print("设备检修知识检索与作业系统 · 性能测试")
    print("目标 %s  账号 %s  采样 %d 次/项" % (BASE, USERNAME, args.rounds))
    print("开始时间 %s" % datetime.now().isoformat(timespec="seconds"))
    print("=" * 66)

    # trust_env=False：本机压测不走系统代理，避免 http(s)_proxy / SOCKS 干扰计时
    async with httpx.AsyncClient(trust_env=False) as cli:
        tok = await login(cli)
        hdr = {"Authorization": "Bearer " + tok}
        print("登录成功\n[响应时间测试]")
        lat = await run_latency(cli, hdr, args.rounds, skip, raw)
        conc = None
        if "concurrency" not in skip:
            conc = await run_concurrency(cli, hdr, args.concurrency, conc_rows)

    stop.set(); th.join(timeout=3)

    # ---- 输出 ----
    write("raw_samples.csv", ["测试项", "序号", "耗时(s)", "时间戳/错误"], raw)
    summary = [[k, v["n"], round(v["avg"], 3), round(v["p50"], 3),
                round(v["p95"], 3), round(v["mx"], 3)] for k, v in lat.items()]
    write("summary.csv", ["测试项", "样本数", "平均值(s)", "P50(s)", "P95(s)", "最大值(s)"], summary)
    if conc_rows:
        write("concurrency.csv", ["请求序号", "耗时(s)", "结果"], conc_rows)
    if res_rows:
        write("resource.csv", ["时间", "后端RSS(MB)", "后端CPU(%)", "系统已用内存(MB)", "系统内存占比(%)"], res_rows)

    lines = []
    lines.append("=" * 66)
    lines.append("性能测试汇总  采集时间 %s" % datetime.now().isoformat(timespec="seconds"))
    lines.append("目标 %s   每项采样 %d 次（已剔除首次冷启动）" % (BASE, args.rounds))
    lines.append("=" * 66)
    lines.append("%-14s %6s %10s %10s %10s %10s" % ("测试项", "样本", "平均(s)", "P50(s)", "P95(s)", "最大(s)"))
    for k, v in lat.items():
        lines.append("%-14s %6d %10.2f %10.2f %10.2f %10.2f"
                     % (k, v["n"], v["avg"], v["p50"], v["p95"], v["mx"]))
    if conc:
        lines.append("")
        lines.append("并发测试：" + "  ".join("%s=%s" % (k, v) for k, v in conc.items()))
    if res_rows:
        peak = max(r[1] for r in res_rows)
        peaksys = max(r[3] for r in res_rows)
        lines.append("资源占用：后端进程峰值 RSS %.0f MB（%.2f GB）；系统峰值已用内存 %.0f MB（%.2f GB）"
                     % (peak, peak / 1024, peaksys, peaksys / 1024))
    txt = "\n".join(lines)
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "report.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print("\n" + txt)
    # 打包成一个文件，便于从 V11 虚拟机下载
    import tarfile
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    pkg = os.path.join(OUTDIR, "benchmark_result_%s.tar.gz" % stamp)
    with tarfile.open(pkg, "w:gz") as tf:
        for fn in os.listdir(OUTDIR):
            if fn.endswith((".csv", ".txt")):
                tf.add(os.path.join(OUTDIR, fn), arcname=fn)
    print("\n全部结果已写入 %s/" % OUTDIR)
    print("已打包：%s   ← 把这一个文件从虚拟机拷出来即可" % pkg)



if __name__ == "__main__":
    asyncio.run(main())
