"""
PROM Service Automation
========================
Automates adding all 7 database services in PROM using Playwright.

Usage:
    uv run playwright install chromium
    uv run python openmetadata_automation/add_services.py
    uv run python openmetadata_automation/add_services.py --db postgresql
    uv run python openmetadata_automation/add_services.py --headless
"""

import argparse
import os
import re
import time
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# =============================================================================
# Config loader
# =============================================================================

def load_config(path: str = None) -> dict:
    config_path = path or Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_env(raw)


def _resolve_env(obj):
    pattern = re.compile(r"\$\{([^}]+)\}")
    if isinstance(obj, str):
        return pattern.sub(lambda m: os.getenv(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _resolve_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env(i) for i in obj]
    return obj


# =============================================================================
# Helpers
# =============================================================================

def fill_by_id(page, field_id: str, value: str):
    """Fill input by PROM JSON Schema id (root/fieldName pattern)."""
    if not value:
        return
    for sel in [
        f'input[id="{field_id}"]',
        f'input[data-testid="{field_id.replace("/", "-")}-input"]',
        f'textarea[id="{field_id}"]',
    ]:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.fill(value)
                print(f"  {field_id.split('/')[-1]}: {value}")
                return
        except Exception:
            continue
    print(f"  [warn] field id '{field_id}' not found")


def fill_tag_testid(page, testid: str, values: list, nth: int = 0):
    """
    Fill tag-input by data-testid + nth.
    Re-clicks before each value to prevent focus drifting to Excludes.
    """
    if not values:
        return
    loc = page.locator(f'[data-testid="{testid}"]').nth(nth)
    try:
        loc.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(300)
    except Exception:
        pass
    for v in values:
        try:
            loc.click(timeout=5000)
            page.wait_for_timeout(200)
            page.keyboard.type(v)
            page.wait_for_timeout(150)
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            print(f"    [{nth}] {testid.split('-')[-2]}: {v}")
        except Exception as e:
            print(f"    [warn] {testid}[{nth}]: {e}")


# =============================================================================
# Connection fillers — one per DB
# =============================================================================

def _fill_postgres(page, cfg):
    fill_by_id(page, "root/username",  cfg.get("username", ""))
    fill_by_id(page, "root/password",  cfg.get("password", ""))
    fill_by_id(page, "root/hostPort",  cfg.get("host_port", ""))
    fill_by_id(page, "root/database",  cfg.get("database", ""))


def _fill_mysql(page, cfg):
    fill_by_id(page, "root/username",     cfg.get("username", ""))
    fill_by_id(page, "root/password",     cfg.get("password", ""))
    fill_by_id(page, "root/hostPort",     cfg.get("host_port", ""))
    fill_by_id(page, "root/databaseName", cfg.get("database", ""))


def _fill_mssql(page, cfg):
    fill_by_id(page, "root/username",  cfg.get("username", ""))
    fill_by_id(page, "root/password",  cfg.get("password", ""))
    fill_by_id(page, "root/hostPort",  cfg.get("host_port", ""))
    fill_by_id(page, "root/database",  cfg.get("database", ""))


def _fill_oracle(page, cfg):
    fill_by_id(page, "root/username",  cfg.get("username", ""))
    fill_by_id(page, "root/password",  cfg.get("password", ""))
    fill_by_id(page, "root/hostPort",  cfg.get("host_port", ""))
    fill_by_id(page, "root/oracleConnectionType/databaseSchema",
               cfg.get("service_name_db", ""))


def _fill_impala(page, cfg):
    fill_by_id(page, "root/username",     cfg.get("username", ""))
    fill_by_id(page, "root/hostPort",     cfg.get("host_port", ""))
    fill_by_id(page, "root/databaseName", cfg.get("database", ""))


def _fill_db2(page, cfg):
    fill_by_id(page, "root/username",  cfg.get("username", ""))
    fill_by_id(page, "root/password",  cfg.get("password", ""))
    fill_by_id(page, "root/hostPort",  cfg.get("host_port", ""))
    fill_by_id(page, "root/database",  cfg.get("database", ""))


def _fill_hive(page, cfg):
    fill_by_id(page, "root/username",       cfg.get("username", ""))
    fill_by_id(page, "root/password",       cfg.get("password", ""))
    fill_by_id(page, "root/hostPort",       cfg.get("host_port", ""))
    fill_by_id(page, "root/databaseName",   cfg.get("database", ""))
    fill_by_id(page, "root/databaseSchema", cfg.get("schema", ""))

    auth = cfg.get("auth", "NONE")
    if auth and auth != "NONE":
        try:
            page.locator('.MuiSelect-select').filter(has_text="NONE").first.click(timeout=5000)
            page.wait_for_timeout(500)
            page.get_by_role("option", name=auth, exact=True).click(timeout=5000)
            print(f"  Authentication Mode: {auth}")
        except Exception as e:
            print(f"  [warn] auth select: {e}")

    meta = cfg.get("metastore", {})
    if meta:
        page.wait_for_timeout(500)
        fill_by_id(page, "root/metastoreConnection/username",          meta.get("username", ""))
        fill_by_id(page, "root/metastoreConnection/hostPort",          meta.get("host_port", ""))
        fill_by_id(page, "root/metastoreConnection/database",          meta.get("database", ""))
        fill_by_id(page, "root/metastoreConnection/authType/password", meta.get("password", ""))


FILLERS = {
    "postgresql": _fill_postgres,
    "mysql":      _fill_mysql,
    "mssql":      _fill_mssql,
    "oracle":     _fill_oracle,
    "impala":     _fill_impala,
    "hive":       _fill_hive,
    "db2":        _fill_db2,
}


# =============================================================================
# Ingestion wizard
# =============================================================================

def _configure_ingestion(page, db_cfg: dict):
    """
    3-step ingestion wizard:
      Step 1: Tier + Includes (x2) + Semantic
      Step 2: Configure Ingestion (uncheck stored procedures if needed)
      Step 3: Add & Deploy
    """
    page.wait_for_timeout(1500)
    ing = db_cfg.get("ingestion", {})

    # ── Step 1 ──────────────────────────────────────────────────────────
    print("  Ingestion Step 1: Metadata Ingestion")

    # Tier — use data-testid="ingestion-tier-select"
    tier = ing.get("tier", "")
    print(f"  [debug] tier={tier}, semantic_count={len(ing.get('semantic', []))}")
    if tier:
        try:
            page.locator('[data-testid="ingestion-tier-select"] .MuiSelect-select').click(timeout=5000)
            # Wait for MUI portal to render options
            page.wait_for_selector(f'li[data-value="Tier.{tier}"]', timeout=5000)
            page.locator(f'li[data-value="Tier.{tier}"]').first.click(timeout=5000)
            page.wait_for_timeout(300)
            print(f"  Tier: {tier}")
        except Exception as e:
            print(f"  [warn] Tier: {e}")

    # Includes — testid appears twice (nth=0 and nth=1)
    for nth in [0, 1]:
        fill_tag_testid(page, "filter-includes-database-input",
                        ing.get("database_includes", []), nth)
        fill_tag_testid(page, "filter-includes-schema-input",
                        ing.get("schema_includes", []),   nth)
        fill_tag_testid(page, "filter-includes-table-input",
                        ing.get("table_includes", []),    nth)

    # Semantic — scroll to section first
    semantic_list = ing.get("semantic", [])
    if semantic_list:
        try:
            page.locator('[data-testid="ingestion-add-semantic-button"]').scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(500)
        except Exception:
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(500)

    for i, sem in enumerate(semantic_list):
        try:
            sem_type = sem.get("type", "")
            column   = sem.get("column", "")
            if not sem_type or not column:
                continue
            if i > 0:
                add_btn = page.locator('[data-testid="ingestion-add-semantic-button"]')
                if add_btn.count() > 0:
                    add_btn.last.click(timeout=3000)
                    page.wait_for_timeout(500)
            dropdowns = page.locator('.MuiAutocomplete-root input[placeholder="Search Semantic"]')
            n = dropdowns.count()
            if n > 0:
                dropdowns.nth(n - 1).click(timeout=3000)
                page.wait_for_timeout(400)
                page.keyboard.type(sem_type[:6])
                page.wait_for_timeout(600)
                page.get_by_role("option").filter(has_text=sem_type).first.click(timeout=3000)
                page.wait_for_timeout(300)
            col_inputs = page.get_by_placeholder("Type column name and press Enter")
            m = col_inputs.count()
            if m > 0:
                col_inputs.nth(m - 1).click(timeout=3000)
                page.keyboard.type(column)
                page.wait_for_timeout(200)
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
            label = sem_type.encode('ascii', errors='replace').decode('ascii')
            print(f"  Semantic[{i}]: {label} -> {column}")
        except Exception as e:
            print(f"  [warn] Semantic[{i}]: {e}")

    page.get_by_role("button", name="Next").last.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # ── Step 2 ──────────────────────────────────────────────────────────
    print("  Ingestion Step 2: Configure Ingestion")

    if not ing.get("include_stored_procedures", True):
        try:
            cb = page.locator('[data-testid="root-includeStoredProcedures-input"]')
            if cb.count() > 0 and cb.is_checked():
                cb.click(timeout=5000)
                print("  Include Stored Procedures: OFF")
        except Exception as e:
            print(f"  [warn] includeStoredProcedures: {e}")

    page.get_by_role("button", name="Next").last.click(timeout=5000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # ── Step 3 ──────────────────────────────────────────────────────────
    print("  Ingestion Step 3: Schedule & Deploy")
    page.screenshot(path="ingestion_step3.png")

    # Try multiple button texts and data-testid
    for selector in [
        'button:has-text("Add & Deploy")',
        'button:has-text("Deploy")',
        'button:has-text("Add and Deploy")',
        '[data-testid="deploy-button"]',
        '[data-testid="workflow-deploy-btn"]',
        'button[type="submit"]',
    ]:
        try:
            btn = page.locator(selector)
            if btn.count() > 0:
                btn.last.click(timeout=10000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                print(f"  Ingestion deployed via: {selector}")
                return
        except Exception:
            continue
    print("  [warn] Add & Deploy button not found — check ingestion_step3.png")


# =============================================================================
# Main automation class
# =============================================================================

class PromAutomation:

    def __init__(self, config: dict, headless: bool = False):
        self.config   = config
        self.om       = config["prom"]
        self.headless = headless
        self.page     = None

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, db_filter: list = None):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, slow_mo=300)
            context = browser.new_context(ignore_https_errors=True)
            self.page = context.new_page()
            self.page.set_default_timeout(20000)
            self._login()

            for db_key, db_cfg in self.config.get("databases", {}).items():
                if db_filter and db_key not in db_filter:
                    continue
                if not db_cfg.get("enabled", True):
                    print(f"[skip] {db_key} disabled")
                    continue
                print(f"\n{'='*55}")
                print(f"  DB: {db_key}  ->  {db_cfg['service_name']}")
                print(f"{'='*55}")
                try:
                    added = self._add_service(db_key, db_cfg)
                    if added and self.config.get("run_ingestion_after_add"):
                        self._trigger_ingestion(db_cfg)
                    print(f"  [OK] {db_key}")
                except Exception as e:
                    err = str(e).encode('ascii', errors='replace').decode('ascii')
                    print(f"  [FAIL] {db_key}: {err}")
                    try:
                        self.page.screenshot(path=f"fail_{db_key}.png")
                    except Exception:
                        pass

            browser.close()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(self):
        print(f"[login] {self.om['url']}")
        self.page.goto(self.om["url"])
        self.page.wait_for_load_state("networkidle")
        # PROM is a React SPA — login form renders after JS executes
        # Wait up to 30s for email input to appear
        self.page.wait_for_selector(
            'input[type="email"], input[id="email"], input[name="email"]',
            timeout=30000
        )

        # Email — click to focus then fill
        email_input = self.page.locator(
            'input[type="email"], input[id="email"], input[name="email"]'
        ).first
        email_input.click(timeout=5000)
        self.page.wait_for_timeout(300)
        email_input.fill(self.om["username"])
        self.page.wait_for_timeout(300)
        print(f"  Email filled: {self.om['username']}")

        # Password — click to focus then fill
        pw_input = self.page.locator(
            'input[type="password"], input[id="password"]'
        ).first
        pw_input.click(timeout=5000)
        self.page.wait_for_timeout(300)
        pw_input.fill(self.om["password"])
        self.page.wait_for_timeout(300)
        print("  Password filled")

        # Submit
        self.page.locator(
            'button[type="submit"], button:has-text("Login")'
        ).first.click(timeout=5000)

        # Wait for login to complete — URL leaves /login and app loads
        try:
            self.page.wait_for_url(
                lambda url: "login" not in url and "signin" not in url,
                timeout=15000
            )
            # Wait for React to fully initialize and store auth token
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(3000)
            print(f"[login] OK — {self.page.url}")
        except Exception:
            self.page.screenshot(path="login_fail.png")
            print(f"[login] FAILED — still on {self.page.url}")
            print("  Check PROM_USER and PROM_PASS in .env")

    # ------------------------------------------------------------------
    # Add Service — 4 steps
    # ------------------------------------------------------------------

    def _add_service(self, db_key: str, db_cfg: dict) -> bool:
        self.page.goto(f"{self.om['url']}/settings-admin/services/databases")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(2000)
        self.page.screenshot(path=f"services_page_{db_key}.png")
        print(f"  URL: {self.page.url}")
        try:
            self.page.wait_for_selector('button:has-text("Add New Service")', timeout=15000)
        except Exception:
            self.page.wait_for_timeout(3000)

        if self.page.get_by_text(db_cfg["service_name"]).count() > 0:
            print(f"  [skip] '{db_cfg['service_name']}' already exists")
            return False

        # Step 1 — Select type
        self.page.get_by_role("button", name="Add New Service").click()
        self.page.wait_for_load_state("networkidle")
        type_map = {
            "postgresql": "Postgres", "impala": "Impala", "hive": "Hive",
            "mysql": "Mysql", "oracle": "Oracle", "mssql": "Mssql", "db2": "Db2",
        }
        self.page.get_by_text(type_map.get(db_key, db_key), exact=True).click()
        self.page.get_by_role("button", name="Next").click()
        self.page.wait_for_load_state("networkidle")

        # Step 2 — Name + Domain
        print("  Step 2: Configure Service")
        self.page.wait_for_timeout(2000)
        for sel in ['input[id="name"]', 'input[name="name"]']:
            try:
                el = self.page.locator(sel)
                if el.count() > 0:
                    el.first.fill(db_cfg["service_name"])
                    break
            except Exception:
                continue

        domain = self.om.get("domain", "")
        if domain:
            try:
                inp = self.page.locator('.MuiAutocomplete-root input').first
                inp.click(timeout=5000)
                self.page.wait_for_timeout(500)
                inp.fill(domain)
                self.page.wait_for_timeout(800)
                self.page.get_by_role("option", name=domain).first.click(timeout=5000)
                print(f"  Domain: {domain} [OK]")
            except Exception as e:
                print(f"  [warn] domain: {e}")

        desc = db_cfg.get("description", "")
        if desc:
            try:
                self.page.locator('div[contenteditable="true"]').first.fill(desc)
            except Exception:
                pass
        self.page.get_by_role("button", name="Next").click()
        self.page.wait_for_load_state("networkidle")

        # Step 3 — Connection Details
        print("  Step 3: Connection Details")
        filler = FILLERS.get(db_key)
        if filler:
            filler(self.page, db_cfg)
        else:
            print(f"  [warn] no filler for {db_key}")

        # Test Connection
        print("  Testing connection...")
        self.page.get_by_role("button", name="Test Connection").click()
        try:
            self.page.wait_for_selector('[data-testid="test-connection-ok-button"]', timeout=60000)
            print("  Connection test: done")
        except Exception:
            print("  Connection test: timeout — proceeding")
        try:
            self.page.locator('[data-testid="test-connection-ok-button"]').click(timeout=5000)
            self.page.wait_for_timeout(500)
        except Exception:
            pass
        self.page.locator('[data-testid="connection-details-save-button"]').click(timeout=10000)
        self.page.wait_for_load_state("networkidle")

        # Step 4 — Default Filters
        try:
            self.page.wait_for_selector('text=Database Filter Pattern', timeout=10000)
            self.page.wait_for_timeout(800)
        except Exception:
            self.page.wait_for_timeout(2000)

        filters = db_cfg.get("filters", {})
        for nth, key in [(0, "database_includes"), (1, "schema_includes"), (2, "table_includes")]:
            values = filters.get(key, [])
            if values:
                fill_tag_testid(self.page, "workflow-includes-input", values, nth)

        for testid in ["save-button", "filter-pattern-modal-save-button"]:
            try:
                btn = self.page.locator(f'[data-testid="{testid}"]')
                if btn.count() > 0:
                    btn.first.click(timeout=5000)
                    break
            except Exception:
                continue
        else:
            try:
                self.page.locator('button[type="submit"]').last.click(timeout=5000)
            except Exception:
                pass
        self.page.wait_for_load_state("networkidle")

        return True

    # ------------------------------------------------------------------
    # Trigger Ingestion
    # ------------------------------------------------------------------

    def _trigger_ingestion(self, db_cfg: dict):
        try:
            self.page.wait_for_selector(
                'button:has-text("Add Ingestion"), [data-testid="add-ingestion-button"]',
                timeout=15000
            )
            print("  Service created successfully!")
            self.page.get_by_role("button", name="Add Ingestion").first.click(timeout=5000)
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(1000)
            print("  Navigated to Add Ingestion")
            _configure_ingestion(self.page, db_cfg)
        except Exception as e:
            print(f"  [warn] Add Ingestion: {e}")


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="PROM Service Automation")
    parser.add_argument("--db", nargs="*",
        help="DB(s): postgresql impala hive mysql oracle mssql db2")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    bot = PromAutomation(config, headless=args.headless)
    bot.run(db_filter=args.db)


if __name__ == "__main__":
    main()
