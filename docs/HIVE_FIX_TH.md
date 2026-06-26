# Hive ACID Fix — เอกสารกระบวนการ

> สรุปการแก้ปัญหา Hive ที่ "เชื่อมต่อได้ แต่ INSERT/DELETE ช้ามากเหมือนค้าง"
> ครอบคลุม: อาการ → วิธีคิด/วิเคราะห์ → สิ่งที่แก้ → วิธีใช้งาน → ข้อควรระวัง

---

## 1. อาการที่เจอ

- เชื่อมต่อ Hive (`HiveServer2 @ 10.10.10.200:10000`) ได้ปกติ
- แต่ `INSERT` ช้ามาก และ `DELETE` ทำไม่ได้เลย
- โดยเฉพาะตอน **close connection แล้วเปิดใหม่** จะช้า/ค้างเป็นนาที

---

## 2. วิธีคิด — ไล่หาสาเหตุ (3 ชั้น)

### ชั้นที่ 1: Hive ไม่ใช่ฐานข้อมูล OLTP

Hive ออกแบบมาเป็น engine แบบ batch/analytics ไม่ใช่ระบบ transaction แบบ
Postgres/MySQL คำสั่ง `INSERT`/`DELETE` ทีละแถวจึงช้าโดยธรรมชาติ เพราะแต่ละ
คำสั่งถูกแปลงเป็น "job" บนคลัสเตอร์

### ชั้นที่ 2: engine เป็น MapReduce (ตัวการความช้า)

จากหน้า YARN ResourceManager เห็นว่า **Application Type = MAPREDUCE**

- query หนึ่งคำสั่งถูกแตกเป็นหลาย stage และ **แต่ละ stage = MR job แยกกัน 1 ตัว**
- MR job แต่ละตัวมี overhead เปิด JVM/container ~15–20 วินาที (job ตัวอย่างใช้
  17 วินาที ทั้งที่ประมวลผลข้อมูลนิดเดียว)
- หลาย stage ต่อกัน → คำสั่งเดียวกินเวลาเป็นนาที = รู้สึกเหมือน "ค้าง"
- สำคัญ: job `SUCCEEDED` ไม่มี preemption ใช้ resource น้อยมาก →
  **คลัสเตอร์ไม่ได้ขาด resource** ปัญหาคือ overhead ของ MapReduce ล้วนๆ

### ชั้นที่ 3: DELETE ทำไม่ได้ + lock ค้างตอน reopen

ตรวจไฟล์ DDL พบว่าตารางสร้างแบบ `STORED AS ORC` เฉยๆ
**ไม่ได้เปิด ACID จริง** (ไม่มี `TBLPROPERTIES('transactional'='true')`)
→ Hive จึงปฏิเสธ `DELETE`/`UPDATE`

และสาเหตุที่ "close แล้วเปิดใหม่ช้า": flow เดิม (`run-all`) รัน Python
**2 process แยกกัน** เปิด/ปิด connection คนละครั้งต่อตาราง บนตาราง ACID การ
close session ที่แตะ transactional table จะทิ้ง **lock** ค้างไว้ และ
connection ถัดไปต้องรอจน lock หมดอายุ (`hive.txn.timeout` ดีฟอลต์
**300 วินาที = 5 นาที**)

---

## 3. สิ่งที่แก้

### 3.1 เปิด ACID จริงในไฟล์ DDL
`database/ddl/water_station/hive.sql` และ `water_station_monitor/hive.sql`

```sql
STORED AS ORC
TBLPROPERTIES (
    'transactional'='true',
    'transactional_properties'='default'   -- เปิด full ACID → INSERT/UPDATE/DELETE ได้
);
```

### 3.2 ตั้ง session properties ให้อัตโนมัติตอน connect
`database/adapters/hive.py → connect()`

ตั้งค่าทุกครั้งที่ต่อ ไม่ต้อง SET เองก่อน DELETE อีก:
- `hive.support.concurrency=true`
- `hive.txn.manager=...DbTxnManager`
- `hive.exec.dynamic.partition.mode=nonstrict`
- รองรับเปลี่ยน engine ผ่าน env `HIVE_EXECUTION_ENGINE` (เช่น `spark`)

### 3.3 ปรับ bulk_load ให้ทำงานกับตาราง ACID
`database/adapters/hive.py → _webhdfs_load()`

ตาราง full-ACID ใช้ `LOAD DATA` ตรงๆ ไม่ได้ จึงเปลี่ยนเป็น:
อัปโหลด CSV → `LOAD DATA` เข้า **staging table** (non-transactional TEXTFILE)
→ `INSERT...SELECT` เข้าตาราง ACID ทีเดียว → drop staging
(ยังเป็น job เดียว เร็วอยู่ และ DELETE ได้)

### 3.4 รวม 2 ตารางไว้ใน connection เดียว
`runners/water_station_both.py` (ไฟล์ใหม่)

เปิด connection ครั้งเดียว → ทำ water_station เสร็จ → ทำ water_station_monitor
เสร็จ → `commit()` → `close()` ครั้งเดียวตอนท้าย
แก้ทั้งความช้าจากการเปิด/ปิดซ้ำ และอาการ lock ค้างตอน reopen

เพิ่มเมธอด `commit()` ใน `HiveAdapter` เพื่อ flush งานก่อนปิด

---

## 4. วิธีใช้งาน

### โหลดทั้ง 2 ตารางใน connection เดียว (แนะนำสำหรับ Hive)
```bash
./run.sh run-both hive
```

### truncate ทั้ง 2 ตาราง แล้วโหลดใหม่ (connection เดียว)
```bash
./run.sh reset-both hive
```

### เรียกตรงๆ ผ่าน Python
```bash
python -m runners.water_station_both --db hive
python -m runners.water_station_both --db hive --reset
```

### แก้ความช้า: เปลี่ยน engine เป็น Spark (ไม่ต้องแก้โค้ด)
```bash
export HIVE_EXECUTION_ENGINE=spark
./run.sh run-both hive
```

---

## 5. ข้อควรระวัง (สำคัญ)

1. **ตารางเดิมไม่กลายเป็น ACID อัตโนมัติ** — `ALTER TABLE ... SET TBLPROPERTIES`
   มักแปลงไม่สำเร็จ ต้อง drop แล้วให้ pipeline สร้างใหม่จาก DDL ที่แก้:
   ```sql
   DROP TABLE demo_dg_db.water_station;
   DROP TABLE demo_dg_db.water_station_monitor;
   ```
   (ถ้ามีข้อมูลต้องเก็บ ให้ย้ายออกก่อน)

2. **ตาราง ACID ใช้ `LOAD DATA` ตรงไม่ได้** — โค้ดแก้ให้ผ่าน staging แล้ว
   แต่ถ้าเขียน SQL เองอย่าลืมข้อนี้

3. **เลือก engine ให้เหมาะกับงาน:**
   - งาน query/ตรวจข้อมูลแบบเร็ว → ใช้ **Impala** (`21051`) ไม่แตะ MapReduce
   - งานเขียน/ETL บน Hive → ตั้ง engine เป็น **spark** ถ้าคลัสเตอร์รองรับ

4. **DAG ปัจจุบัน** (`dataquality_water_station_monitoring`) ยังเรียกแบบ 2 process
   อยู่ — ถ้าต้องการให้ Hive ไม่ค้าง ควรเปลี่ยนให้เรียก `run-both`

---

## 6. ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | การเปลี่ยนแปลง |
|------|----------------|
| `database/ddl/water_station/hive.sql` | เปิด ACID |
| `database/ddl/water_station_monitor/hive.sql` | เปิด ACID |
| `database/adapters/hive.py` | session props, engine override, staging load, `commit()` |
| `runners/water_station_both.py` | **ไฟล์ใหม่** — 2 ตาราง / 1 connection |
| `run.sh` | คำสั่งใหม่ `run-both`, `reset-both` |

> หมายเหตุ: การแก้นี้ตรวจ syntax/compile ผ่านแล้ว แต่ยังไม่ได้ทดสอบกับ Hive
> จริง (รันจากเครื่องที่ต่อคลัสเตอร์ได้เท่านั้น) แนะนำรัน `run-both hive`
> ครั้งแรกแล้วสังเกตเวลา/ผลลัพธ์
