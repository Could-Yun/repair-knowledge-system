#!/usr/bin/env python3
"""
数据库初始化脚本：建表 + 创建默认账号 + 创建默认设备类型 + 写入演示工作流模板

用法:
  python3 scripts/init_db.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

DEMO_WORKFLOW = [
    {"step": 1, "title": "安全检查与断电", "desc": "关闭点火开关，断开蓄电池负极，确认发动机完全冷却（冷却液温度 < 40°C）。", "checks": ["已关闭点火开关", "已断开蓄电池负极", "悬挂警示牌"], "risk": "触电/烫伤", "tools": []},
    {"step": 2, "title": "拆卸外部附件", "desc": "拆除化油器、空滤器、排气管等外围附件，注意标记螺栓位置。", "checks": [], "risk": "机械伤害", "tools": ["十字螺丝刀", "内六角扳手", "梅花扳手"]},
    {"step": 3, "title": "拆卸气缸盖", "desc": "按对角顺序拧松气缸盖螺母，拆除气门室罩、气缸盖，检查缸垫。", "checks": ["已确认冷却液排尽（水冷型）"], "risk": "密封件损坏", "tools": ["套筒扳手", "扭力扳手"]},
    {"step": 4, "title": "检查与测量", "desc": "测量气缸磨损量、活塞环间隙、气门间隙，记录数据并与标准值对比。", "checks": [], "risk": "", "tools": ["千分尺", "游标卡尺", "厚薄规"]},
    {"step": 5, "title": "更换损坏件", "desc": "根据检查结果更换活塞环、气门油封、缸垫等损坏零件，注意配合面清洁。", "checks": [], "risk": "零件损坏", "tools": ["活塞环拆装钳", "橡皮锤"]},
    {"step": 6, "title": "回装与紧固", "desc": "按拆卸逆序回装，气缸盖螺母按规定扭矩（参见手册）对角紧固。", "checks": ["回装螺栓已全部紧固", "缸垫已更换"], "risk": "", "tools": ["扭力扳手"]},
    {"step": 7, "title": "试运行验证", "desc": "启动发动机，怠速运行 5 分钟，检查是否有漏油、漏气、异响现象。", "checks": ["无漏油", "无漏气", "无异响"], "risk": "", "tools": []},
]

async def init():
    from app.database import async_session, engine, Base, check_connection
    from app.models.user import User
    from app.models.device import DeviceType
    from app.models.workflow import WorkflowTemplate
    from app.utils.security import hash_password
    from sqlalchemy import select

    # 连通性 + 扩展自动启用
    await check_connection()

    # 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[INFO] 数据库建表完成")

    async with async_session() as db:
        # 创建管理员账号
        if not (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none():
            db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin", real_name="系统管理员"))
            print("[INFO] 创建账号: admin / admin123")

        # 创建一线人员账号
        if not (await db.execute(select(User).where(User.username == "worker"))).scalar_one_or_none():
            db.add(User(username="worker", password_hash=hash_password("worker123"), role="field_worker", real_name="测试工人", department="发动机维修车间"))
            print("[INFO] 创建账号: worker / worker123")

        await db.flush()

        # 创建设备类型
        device_names = ["摩托车发动机", "数控机床 CK6136", "液压系统", "电气控制系统", "传动系统"]
        device_ids = {}
        for name in device_names:
            if not (await db.execute(select(DeviceType).where(DeviceType.name == name))).scalar_one_or_none():
                d = DeviceType(name=name, category="发动机" if "发动机" in name else "机械")
                db.add(d)
                await db.flush()
                device_ids[name] = d.id
                print(f"[INFO] 创建设备类型: {name}")
            else:
                d = (await db.execute(select(DeviceType).where(DeviceType.name == name))).scalar_one()
                device_ids[name] = d.id

        # 获取 admin 用户 id
        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()

        # 创建演示作业模板
        moto_id = device_ids.get("摩托车发动机")
        if moto_id and not (await db.execute(select(WorkflowTemplate).where(WorkflowTemplate.name == "摩托车发动机大修流程"))).scalar_one_or_none():
            db.add(WorkflowTemplate(
                device_type_id=moto_id,
                repair_level="major",
                name="摩托车发动机大修流程",
                steps=DEMO_WORKFLOW,
                estimated_duration=180,
                created_by=admin.id,
            ))
            print("[INFO] 创建演示工作流: 摩托车发动机大修流程")

        await db.commit()

    # 建索引（SKILL 02 §3）；IVFFlat 在空表上可建，seed 后重跑 create_indexes.py 效果更佳
    try:
        from scripts.create_indexes import create_indexes
        await create_indexes(lists=100)
    except Exception as e:
        print(f"[WARN] 索引创建失败（不阻塞初始化，可稍后手动 python3 scripts/create_indexes.py）: {e}")

    print("[DONE] 初始化完成！")
    print("  管理员账号: admin / admin123")
    print("  一线人员:   worker / worker123")

if __name__ == "__main__":
    asyncio.run(init())
