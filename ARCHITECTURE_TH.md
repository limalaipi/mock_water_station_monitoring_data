# อธิบาย ARCHITECTURE.md
## หลักการออกแบบ (Design Philosophy)

---

## สถาปัตยกรรมนี้สร้างขึ้นจากปัญหาที่พบในโค้ดปัจจุบัน 4 ข้อ:
**1. ใช้ Config แทนการ Hardcode** — ค่าทุกอย่างที่อาจเปลี่ยนแปลงได้ เช่น host, port, column rules, threshold ต่างๆ ให้เก็บไว้ใน YAML file แทนที่จะเขียนตรงในโค้ด Python การเปลี่ยน scenario ทดสอบ = แก้ไขไฟล์ YAML เท่านั้น
**2. Adapter รู้แค่วิธีเชื่อมต่อ DB** — ไม่รู้เรื่องธุรกิจ — แต่ละ adapter (PostgreSQL, Hive, ฯลฯ) รู้แค่วิธีเชื่อมต่อ, สร้างตาราง, และ load ข้อมูล ไม่มีโค้ดที่เกี่ยวกับ water station อยู่ใน adapter เลย
**3. Runner ทำหน้าที่แค่ประสาน** — ไฟล์ runner มีหน้าที่เพียงอ่าน config → ดึง adapter → รัน pipeline → โหลดข้อมูล เท่านั้น ไม่มี class definition, SQL, หรือ JSON parsing
**4.** เพิ่ม Database ใหม่ = เพิ่มไฟล์ใหม่เท่านั้น — ไม่ต้องแก้ไฟล์เดิมเลย

---

## Design Patterns ที่ใช้

### Factory Pattern — ConnectionFactory
เป็นตัวกลางในการสร้าง adapter ส่วนอื่นของระบบไม่ต้อง import PostgresAdapter หรือ HiveAdapter โดยตรง แค่ถามจาก factory ว่าต้องการ DB ชนิดไหน

```
ConnectionFactory.get("hive")      → ได้ HiveAdapter
ConnectionFactory.get("postgresql") → ได้ PostgresAdapter
```

### Strategy Pattern — BulkLoader
แต่ละ adapter ซ่อนวิธีการ load ข้อมูลของตัวเองไว้ภายใน runner แค่เรียก `adapter.bulk_load(df, schema, table)` โดยไม่ต้องรู้ว่าข้างในใช้ `COPY`, `LOAD DATA INFILE`, หรือ `batch insert`

### Template Method Pattern — BaseAdapter
คลาสแม่กำหนดโครงสร้างการทำงาน: `connect()` → `ensure_table_exists()` → `bulk_load()` → `close()` คลาสลูก override เฉพาะส่วนที่แตกต่าง เช่น Hive และ Impala ที่ไม่มี information_schema
Repository Pattern — PipelineStateRepository

### Repository Pattern — `PipelineStateRepository`
การอ่าน/เขียน config.json ทั้งหมดอยู่ใน class นี้ที่เดียว pipeline ไม่เรียก `json.load()` หรือ `json.dump()` โดยตรง ทำให้วันหน้าถ้าจะเปลี่ยนจากเก็บใน file เป็นเก็บใน database ก็แก้แค่ที่นี่ที่เดียว

---

## 3. Directory Tree

```
water_station_monitoring/
│
├── .env.example          ← template ค่า environment variable ทั้งหมด
├── config/               ← ไฟล์ YAML เท่านั้น ไม่มี Python
│   ├── connections.yaml          อ้างอิง ${ENV_VAR} จาก .env
│   ├── pipeline_water_station.yaml   scenario ที่ 1
│   └── pipeline_water_quality.yaml   scenario ที่ 2
│
├── database/             ← ทุกอย่างเกี่ยวกับ DB อยู่ที่นี่
│   ├── factory.py            ลงทะเบียน adapter ทุกตัว
│   ├── adapters/
│   │   ├── base.py           สัญญา (interface) ที่ทุก adapter ต้องทำตาม
│   │   ├── postgres.py       implement สำหรับ PostgreSQL
│   │   ├── hive.py           implement สำหรับ Hive
│   │   └── ... (อีก 5 ตัว)
│   └── ddl/
│       └── water_station_monitor/
│           ├── postgresql.sql    DDL สำหรับสร้างตาราง
│           ├── hive.sql
│           └── ... (อีก 5 ตัว)
│
├── pipeline/             ← logic ทั้งหมดเกี่ยวกับ data pipeline
│   ├── models.py     Enum + Dataclass ทั้งหมด (แหล่งความจริงที่เดียว)
│   ├── quality.py    ฟังก์ชันคำนวณ quality (pure Python ไม่ต้องการ DB)
│   ├── generators.py สร้าง row + ใส่ corruption ตาม strategy
│   ├── state.py      อ่าน/เขียน config.json (Repository Pattern)
│   └── etl.py        orchestrate การรัน ETL แต่ละวัน
│
├── config_loader/        ← แปลง YAML → dataclass objects
│   ├── pipeline_config.py    อ่าน pipeline_*.yaml
│   └── connection_config.py  อ่าน connections.yaml + .env
│
├── runners/              ← entry point บางๆ ~50 บรรทัด
│   ├── water_station.py          ใช้ pipeline_water_station.yaml
│   └── water_station_quality.py  ใช้ pipeline_water_quality.yaml
│
├── tests/
│   ├── unit/         ทดสอบโดยไม่ต้องเชื่อมต่อ DB เลย
│   └── integration/  ทดสอบต่อ DB จริง (ข้าม test อัตโนมัติถ้าไม่มี env var)
│
└── requirements/     แยก dependency ตาม DB แต่ละตัว
```

---

## Flow การทำงาน

### เริ่มต้น
```
  ├─ โหลด .env
  ├─ อ่าน pipeline_*.yaml → ได้ DataQualityConfig + ColumnQualityConfig + Settings
  ├─ อ่าน connections.yaml + .env → ได้ค่าเชื่อมต่อ DB
  ├─ ConnectionFactory.get("hive") → ได้ HiveAdapter
  └─ adapter.connect()
```


### ตรวจสอบตาราง
```
  ├─ adapter.table_exists() → ไม่มีตาราง
  └─ โหลด ddl/water_station_monitor/hive.sql → สร้างตารางอัตโนมัติ
```

### รัน ETL
```
  ├─ โหลด state จาก config.json (วันที่เท่าไหร่แล้ว, สะสมกี่ row)
  ├─ สร้าง row ใหม่พร้อม UUID (ไม่ง้อ DB auto-increment)
  ├─ ใส่ corruption ตาม column rules ของวันนั้น
  ├─ adapter.bulk_load(df) → เลือก COPY / LOAD DATA / batch insert อัตโนมัติ
  ├─ บันทึก state กลับ config.json
  └─ save CSV ของวันนั้น
```

### ปิดการเชื่อมต่อ
```
  └─ adapter.close()
```