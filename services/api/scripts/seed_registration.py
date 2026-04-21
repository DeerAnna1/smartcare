"""
注册挂号模块种子数据脚本
用法: docker exec med_api python3 /app/scripts/seed_registration.py
"""
import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@med_postgres:5432/med_help"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


HOSPITALS = [
    {
        "id": "hosp-001",
        "name": "北京协和医院",
        "city": "北京",
        "address": "北京市东城区帅府园1号",
        "level": "三级甲等",
        "phone": "010-69156114",
        "is_active": True,
    },
    {
        "id": "hosp-002",
        "name": "北京大学人民医院",
        "city": "北京",
        "address": "北京市西城区西直门南大街11号",
        "level": "三级甲等",
        "phone": "010-88324422",
        "is_active": True,
    },
    {
        "id": "hosp-003",
        "name": "复旦大学附属中山医院",
        "city": "上海",
        "address": "上海市徐汇区枫林路180号",
        "level": "三级甲等",
        "phone": "021-64041990",
        "is_active": True,
    },
]

# (hospital_id, dept_id, name, specialty, description)
DEPARTMENTS = [
    ("hosp-001", "dept-001-nei", "内科", "内科综合诊疗", "负责心血管、呼吸、消化等常见内科疾病"),
    ("hosp-001", "dept-001-wai", "外科", "外科综合诊疗", "普外科、胸外科等外科疾病手术治疗"),
    ("hosp-001", "dept-001-xin", "心血管内科", "心脏病专科", "心脏病、高血压、心律失常等"),
    ("hosp-001", "dept-001-shen", "肾内科", "肾脏病专科", "肾炎、慢性肾病、肾衰竭等"),
    ("hosp-002", "dept-002-nei", "内科", "内科综合诊疗", "心血管、呼吸、消化、内分泌等内科疾病"),
    ("hosp-002", "dept-002-tang", "内分泌科", "糖尿病与代谢病", "糖尿病、甲状腺疾病、代谢综合征"),
    ("hosp-002", "dept-002-hu",  "呼吸内科", "呼吸系统疾病", "哮喘、COPD、肺炎等呼吸疾病"),
    ("hosp-003", "dept-003-gan", "肝脏外科", "肝胆外科专科", "肝炎、肝癌、肝硬化手术治疗"),
    ("hosp-003", "dept-003-xiao", "消化内科", "消化系统疾病", "胃炎、肠炎、消化道肿瘤等"),
]

# 生成滚动7天排班
SCHEDULE_TEMPLATES = [
    # (dept_id, doctor_name, title, bio, time_slot, fee, quota)
    ("dept-001-nei", "张明", "主治医师", "擅长高血压、糖尿病管理，执业20年", "08:30", 45.0, 20),
    ("dept-001-nei", "李华", "副主任医师", "心血管内科专家，擅长冠心病诊疗", "10:00", 80.0, 15),
    ("dept-001-nei", "王芳", "主任医师", "内科主任，国家级名医，诊治疑难杂症", "14:30", 200.0, 10),
    ("dept-001-xin", "陈刚", "主任医师", "心血管内科主任，擅长复杂心律失常", "09:00", 300.0, 8),
    ("dept-001-xin", "刘静", "副主任医师", "擅长高血压并发症及心力衰竭管理", "14:00", 150.0, 12),
    ("dept-001-shen", "赵磊", "主任医师", "肾脏病专家，擅长慢性肾病综合管理", "09:30", 200.0, 10),
    ("dept-002-nei", "孙伟", "副主任医师", "擅长内科综合诊疗，尤其代谢性疾病", "08:30", 60.0, 20),
    ("dept-002-tang", "周洁", "主任医师", "内分泌科主任，糖尿病国家级专家", "09:00", 300.0, 8),
    ("dept-002-tang", "吴磊", "主治医师", "擅长2型糖尿病及甲状腺结节处理", "14:00", 80.0, 15),
    ("dept-002-hu",  "郑秀", "副主任医师", "呼吸内科专家，擅长哮喘及COPD管理", "10:00", 120.0, 12),
    ("dept-003-gan", "黄涛", "主任医师", "肝胆外科主任，擅长腹腔镜肝切除术", "08:30", 400.0, 6),
    ("dept-003-xiao", "林晨", "主治医师", "擅长消化内镜及炎症性肠病诊治", "10:30", 80.0, 18),
]


async def seed():
    async with AsyncSessionLocal() as db:
        # ── 检查是否已有数据 ──────────────────────────────────────────────────────
        result = await db.execute(text("SELECT COUNT(*) FROM hospitals"))
        count = result.scalar()
        if count and count > 0:
            print(f"[seed] hospitals 表已有 {count} 条数据，跳过重复插入。")
            return

        # ── 插入医院 ──────────────────────────────────────────────────────────────
        for h in HOSPITALS:
            short_name = h["name"][:4]  # 取前4字作简称
            await db.execute(
                text("""
                    INSERT INTO hospitals
                        (id, name, short_name, city, district, address, level, phone,
                         tags, platform_code, platform_type, booking_url, is_active, created_at)
                    VALUES
                        (:id, :name, :short_name, :city, '', :address, :level, :phone,
                         '[]', '', 'seed', '', :is_active, NOW())
                    ON CONFLICT (id) DO NOTHING
                """),
                {**h, "short_name": short_name}
            )
        print(f"[seed] 插入 {len(HOSPITALS)} 家医院")

        # ── 插入科室 ──────────────────────────────────────────────────────────────
        for hospital_id, dept_id, name, specialty, description in DEPARTMENTS:
            await db.execute(
                text("""
                    INSERT INTO departments
                        (id, hospital_id, name, code, category, description, floor, is_active, created_at)
                    VALUES
                        (:id, :hospital_id, :name, '', :category, :description, '', TRUE, NOW())
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": dept_id,
                    "hospital_id": hospital_id,
                    "name": name,
                    "category": specialty,
                    "description": description,
                }
            )
        print(f"[seed] 插入 {len(DEPARTMENTS)} 个科室")

        # ── 插入7天排班 ───────────────────────────────────────────────────────────
        today = date.today()
        schedule_count = 0
        for day_offset in range(7):
            target_date = today + timedelta(days=day_offset)
            date_str = target_date.strftime("%Y-%m-%d")
            weekday = target_date.weekday()  # 周一=0, 周日=6
            # 周末减少排班量（主任医师不出诊）
            for dept_id, doctor, title, bio, time_slot, fee, quota in SCHEDULE_TEMPLATES:
                if weekday >= 5 and title == "主任医师":
                    continue  # 周末主任不出诊
                adjusted_quota = max(5, quota - day_offset)  # 越近号源越多
                sched_id = f"sched-{dept_id[-3:]}-{doctor}-{date_str}"
                await db.execute(
                    text("""
                        INSERT INTO doctor_schedules
                            (id, department_id, doctor_name, doctor_title, doctor_bio,
                             schedule_date, time_slot, period, fee, total_quota, remaining_quota,
                             platform_slot_id, is_available, updated_at)
                        VALUES
                            (:id, :dept_id, :doctor, :title, :bio,
                             :schedule_date, :time_slot, '上午', :fee, :total_quota, :remaining_quota,
                             '', TRUE, NOW())
                        ON CONFLICT (id) DO NOTHING
                    """),
                    {
                        "id": sched_id,
                        "dept_id": dept_id,
                        "doctor": doctor,
                        "title": title,
                        "bio": bio,
                        "schedule_date": date_str,
                        "time_slot": time_slot,
                        "fee": fee,
                        "total_quota": quota,
                        "remaining_quota": adjusted_quota,
                    }
                )
                schedule_count += 1

        print(f"[seed] 插入 {schedule_count} 条排班记录（7天）")
        await db.commit()
        print("[seed] ✅ 种子数据插入完成！")


if __name__ == "__main__":
    asyncio.run(seed())
