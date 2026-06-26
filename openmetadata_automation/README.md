# OpenMetadata Service Automation

Playwright script สำหรับ add database services ทั้ง 7 ตัวใน OpenMetadata อัตโนมัติ

## Setup (ครั้งแรก)

```bash
cd openmetadata_automation

# ติดตั้ง Playwright
uv add playwright pyyaml python-dotenv
uv run playwright install chromium
```

## ตั้งค่า

แก้ไข `config.yaml`:
- `openmetadata.url` — URL ของ OpenMetadata
- `openmetadata.username` — email login
- แต่ละ DB: host_port, username, database

ใส่ password ใน `.env` (project root):
```env
OM_PASSWORD=your_openmetadata_password
POSTGRES_PASS=...
MYSQL_PASS=...
# etc.
```

## รัน

```bash
# รันทุก DB
uv run python add_services.py

# รัน DB เดียว
uv run python add_services.py --db postgresql

# รันหลาย DB
uv run python add_services.py --db postgresql mysql oracle

# ไม่แสดง browser (background)
uv run python add_services.py --headless
```
