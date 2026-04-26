"""
setup_pos_profile.py — Configuración completa de Punto de Venta en ERPNext v16
===============================================================================
Automatiza los 4 pasos del setup de POS:
  1. Crear POS Profile con compañía, depósito y cuentas contables
  2. Asignar usuarios al perfil (Applicable Users)
  3. Configurar Modos de Pago con sus cuentas contables
  4. Crear la Apertura de Caja (POS Opening Entry) con saldo inicial

Prerequisitos:
  - Empresa creada (init_company.run)
  - Depósito creado
  - Modos de pago con cuentas configuradas (init_company.run)
  - Usuarios creados

Uso — perfil completo:
    bench --site erp.chamigo.com.py execute frappe.setup_pos_profile.run \\
        --kwargs '{
            "company": "Chamigo E.A.S",
            "pos_name": "Caja Principal - Sucursal Norte",
            "warehouse": "Depósito Central - CHA",
            "cashier_emails": ["cajero@chamigo.com.py"],
            "opening_amount": 500000
        }'

Uso — solo crear perfil (sin apertura):
    bench --site erp.chamigo.com.py execute frappe.setup_pos_profile.run \\
        --kwargs '{
            "company": "Chamigo E.A.S",
            "pos_name": "Caja 2 - Mostrador",
            "warehouse": "Depósito Ventas - CHA",
            "cashier_emails": ["ventas@chamigo.com.py"]
        }'

Uso — solo apertura de caja en un perfil existente:
    bench --site erp.chamigo.com.py execute frappe.setup_pos_profile.open_shift \\
        --kwargs '{
            "pos_profile": "Caja Principal - Sucursal Norte",
            "cashier_email": "cajero@chamigo.com.py",
            "opening_amount": 500000
        }'
"""

import frappe
from frappe.utils import nowdate, now_datetime


def log(msg, level="INFO"):
    prefix = {"INFO": "✔", "WARN": "⚠", "ERROR": "✖", "SKIP": "·"}.get(level, " ")
    print(f"  [{level}] {prefix} {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de cuenta contable
# ─────────────────────────────────────────────────────────────────────────────

def find_account(company, *names, account_type=None):
    """Busca una cuenta por nombre (varios intentos) o por tipo."""
    for name in names:
        result = frappe.db.get_value(
            "Account",
            {"company": company, "account_name": name, "is_group": 0},
            "name",
        )
        if result:
            return result
    if account_type:
        return frappe.db.get_value(
            "Account",
            {"company": company, "account_type": account_type, "is_group": 0},
            "name",
        )
    return None


def get_company_accounts(company):
    """Resuelve las cuentas estándar de la empresa."""
    return {
        "income":    find_account(company, "Sales", "Ventas", account_type="Income Account"),
        "expense":   find_account(company, "Cost of Goods Sold", account_type="Expense Account"),
        "writeoff":  find_account(company, "Write Off", "Diferencias de Caja", "Round Off"),
        "cash":      find_account(company, "Caja General", "Cash", account_type="Cash"),
        "bank":      find_account(company, "Banco Principal", "Bank Accounts", account_type="Bank"),
    }


def get_cost_center(company):
    return frappe.db.get_value(
        "Cost Center",
        {"company": company, "is_group": 0},
        "name",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Paso 1 — Cliente genérico
# ─────────────────────────────────────────────────────────────────────────────

def ensure_generic_customer(company, name="Consumidor Final"):
    if frappe.db.exists("Customer", name):
        return name

    if not frappe.db.exists("Customer Group", "Retail"):
        frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": "Retail",
            "parent_customer_group": "All Customer Groups",
        }).insert(ignore_permissions=True)

    frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name,
        "customer_type": "Individual",
        "customer_group": "Retail",
        "territory": "All Territories",
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"Cliente genérico creado: {name}")
    return name


# ─────────────────────────────────────────────────────────────────────────────
# Paso 2 — Lista de precios
# ─────────────────────────────────────────────────────────────────────────────

def ensure_price_list(name="Lista POS", currency="PYG"):
    if frappe.db.exists("Price List", name):
        return name
    frappe.get_doc({
        "doctype": "Price List",
        "price_list_name": name,
        "currency": currency,
        "selling": 1,
        "buying": 0,
        "enabled": 1,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"Price List creada: {name}")
    return name


# ─────────────────────────────────────────────────────────────────────────────
# Paso 3 — Modos de pago (Payments) del perfil
# ─────────────────────────────────────────────────────────────────────────────

def build_payment_rows(company, extra_payments=None):
    """
    Construye la tabla de modos de pago para el POS Profile.
    Lee los Mode of Payment que tienen cuenta configurada para la empresa.
    extra_payments permite forzar entradas adicionales:
        [{"mode_of_payment": "Efectivo", "account": "Caja General - CHA", "default": 1}]
    """
    rows = []
    seen = set()

    # Modos de pago configurados para la empresa
    mops = frappe.get_all("Mode of Payment", fields=["name", "type"], order_by="name")
    for mop in mops:
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mop.name, "company": company},
            "default_account",
        )
        if not account:
            continue
        rows.append({
            "mode_of_payment": mop.name,
            "account": account,
            "default": 1 if mop.name == "Efectivo" else 0,
        })
        seen.add(mop.name)

    # Entradas adicionales forzadas
    for ep in (extra_payments or []):
        if ep["mode_of_payment"] not in seen:
            rows.append(ep)

    if not rows:
        log("No se encontraron modos de pago con cuentas para esta empresa", "WARN")

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Paso 4 — POS Profile (creación o actualización)
# ─────────────────────────────────────────────────────────────────────────────

def create_pos_profile(
    company,
    pos_name,
    warehouse,
    cashier_emails,
    price_list="Lista POS",
    customer="Consumidor Final",
    tax_template=None,
    extra_payments=None,
    currency="PYG",
):
    """
    Crea el POS Profile completo con:
      - Datos de empresa y depósito
      - Cuentas contables automáticas
      - Usuarios habilitados (Applicable Users)
      - Modos de pago con cuentas
    """
    if frappe.db.exists("POS Profile", pos_name):
        log(f"POS Profile ya existe: {pos_name} — actualizando usuarios...", "WARN")
        _add_users_to_profile(pos_name, cashier_emails)
        return pos_name

    accounts     = get_company_accounts(company)
    cost_center  = get_cost_center(company)

    # Plantilla de IVA: usar la default si no se especifica
    if not tax_template:
        tax_template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {"company": company, "is_default": 1},
            "name",
        )

    # Validaciones mínimas
    if not accounts["income"]:
        log("No se encontró cuenta de ingresos — configurar COA primero", "ERROR")
        return None
    if not warehouse:
        log("Warehouse es obligatorio", "ERROR")
        return None

    # Usuarios habilitados
    user_rows = _build_user_rows(cashier_emails)

    # Pagos
    payment_rows = build_payment_rows(company, extra_payments)

    doc = frappe.get_doc({
        "doctype":            "POS Profile",
        "name":               pos_name,   # requerido en ERPNext v16 (naming: Prompt)
        "pos_profile_name":   pos_name,
        "company":            company,
        "warehouse":          warehouse,
        "currency":           currency,
        "selling_price_list": price_list,
        "customer":           customer,
        "taxes_and_charges":  tax_template,
        "cost_center":        cost_center,
        "income_account":     accounts["income"],
        "expense_account":    accounts["expense"],
        "write_off_account":  accounts["writeoff"] or accounts["income"],
        "write_off_cost_center": cost_center,
        # Opciones de comportamiento
        "validate_stock_on_save":          1,
        "hide_images":                     0,
        "allow_discount_change":           1,
        "allow_rate_change":               0,
        # Tablas hijas
        "applicable_for_users": user_rows,
        "payments":             payment_rows,
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    log(f"POS Profile creado: {pos_name}")
    log(f"  Empresa      : {company}")
    log(f"  Depósito     : {warehouse}")
    log(f"  Cuenta ventas: {accounts['income']}")
    log(f"  Cuenta caja  : {accounts['cash']}")
    log(f"  IVA template : {tax_template or '(ninguno)'}")
    log(f"  Cajeros      : {[r['user'] for r in user_rows]}")
    log(f"  Pagos        : {[r['mode_of_payment'] for r in payment_rows]}")

    return pos_name


def _build_user_rows(cashier_emails):
    rows = []
    for i, email in enumerate(cashier_emails):
        if not frappe.db.exists("User", email):
            log(f"Usuario no encontrado, skip: {email}", "WARN")
            continue
        rows.append({"user": email, "default": 1 if i == 0 else 0})
    return rows


def _add_users_to_profile(pos_name, cashier_emails):
    """Agrega usuarios a un POS Profile existente."""
    doc = frappe.get_doc("POS Profile", pos_name)
    existing = {r.user for r in doc.applicable_for_users}
    added = 0
    for email in cashier_emails:
        if email not in existing and frappe.db.exists("User", email):
            doc.append("applicable_for_users", {"user": email, "default": 0})
            added += 1
    if added:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        log(f"{added} usuario(s) agregado(s) al perfil: {pos_name}")
    else:
        log("Todos los usuarios ya estaban en el perfil", "SKIP")


# ─────────────────────────────────────────────────────────────────────────────
# Paso 5 — Apertura de Caja (POS Opening Entry)
# ─────────────────────────────────────────────────────────────────────────────

def open_shift(
    pos_profile: str,
    cashier_email: str,
    opening_amount: float = 0.0,
):
    """
    Crea y envía una POS Opening Entry (apertura de caja).

    El sistema solo permite una apertura activa por perfil+usuario a la vez.
    Si ya hay una abierta, informa y no crea una nueva.

    Args:
        pos_profile    : Nombre exacto del POS Profile
        cashier_email  : Email del cajero que abre la caja
        opening_amount : Efectivo inicial en caja (en PYG)

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_pos_profile.open_shift \\
            --kwargs '{
                "pos_profile": "Caja Principal - Sucursal Norte",
                "cashier_email": "cajero@chamigo.com.py",
                "opening_amount": 500000
            }'
    """
    # Validar que el cajero exista y esté activo
    if not frappe.db.exists("User", cashier_email):
        log(f"Usuario no encontrado: {cashier_email}", "ERROR")
        return None

    user_enabled = frappe.db.get_value("User", cashier_email, "enabled")
    if not user_enabled:
        log(f"Usuario deshabilitado: {cashier_email} — habilitarlo primero", "ERROR")
        return None

    # La apertura se crea como Administrator pero con user=cajero
    frappe.set_user("Administrator")

    if not frappe.db.exists("POS Profile", pos_profile):
        log(f"POS Profile no encontrado: {pos_profile}", "ERROR")
        return None

    # Verificar si ya hay una apertura activa
    existing_open = frappe.db.get_value(
        "POS Opening Entry",
        {
            "pos_profile": pos_profile,
            "docstatus": 1,
            "status": "Open",
        },
        "name",
    )
    if existing_open:
        log(f"Ya existe una apertura activa: {existing_open} — cerrarla antes de abrir una nueva", "WARN")
        return existing_open

    # Obtener modos de pago del perfil para la apertura
    profile_doc = frappe.get_doc("POS Profile", pos_profile)
    opening_details = []

    for payment in profile_doc.payments:
        amount = opening_amount if payment.mode_of_payment == "Efectivo" else 0.0
        opening_details.append({
            "mode_of_payment": payment.mode_of_payment,
            "opening_amount":  amount,
        })

    if not opening_details:
        log("El perfil no tiene modos de pago configurados", "ERROR")
        return None

    doc = frappe.get_doc({
        "doctype":              "POS Opening Entry",
        "pos_profile":          pos_profile,
        "user":                 cashier_email,      # campo obligatorio en v16
        "company":              profile_doc.company,
        "pos_opening_time":     now_datetime(),
        "period_start_date":    nowdate(),
        "balance_details":      opening_details,
    })

    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()

    log(f"Apertura de caja creada y enviada: {doc.name}")
    log(f"  Perfil  : {pos_profile}")
    log(f"  Cajero  : {cashier_email}")
    log(f"  Efectivo: {opening_amount:,.0f} PYG")

    return doc.name


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada principal
# ─────────────────────────────────────────────────────────────────────────────

def run(
    company: str,
    pos_name: str,
    warehouse: str,
    cashier_emails: list = None,
    price_list: str = "Lista POS",
    customer_name: str = "Consumidor Final",
    tax_template: str = None,
    opening_amount: float = 0.0,
    currency: str = "PYG",
):
    """
    Ejecuta el flujo completo de configuración de POS:
      1. Asegura cliente genérico y lista de precios
      2. Crea el POS Profile con usuarios y modos de pago
      3. Si opening_amount > 0, crea la apertura de caja

    Args:
        company        : Empresa                 ej: "Chamigo E.A.S"
        pos_name       : Nombre del POS          ej: "Caja Principal - Sucursal Norte"
        warehouse      : Depósito                ej: "Depósito Central - CHA"
        cashier_emails : Lista de cajeros        ej: ["cajero@chamigo.com.py"]
        price_list     : Lista de precios
        customer_name  : Cliente genérico
        tax_template   : Plantilla IVA (None = usa la default)
        opening_amount : Efectivo inicial (0 = no abre caja automáticamente)
        currency       : Moneda

    Uso completo:
        bench --site erp.chamigo.com.py execute frappe.setup_pos_profile.run \\
            --kwargs '{
                "company": "Chamigo E.A.S",
                "pos_name": "Caja Principal - Sucursal Norte",
                "warehouse": "Depósito Central - CHA",
                "cashier_emails": ["cajero@chamigo.com.py"],
                "opening_amount": 500000
            }'
    """
    frappe.set_user("Administrator")
    cashier_emails = cashier_emails or []

    print(f"\n{'═' * 56}")
    print(f"  POS Setup — {pos_name}")
    print(f"{'═' * 56}\n")

    try:
        # 1. Prereqs
        ensure_generic_customer(company, customer_name)
        ensure_price_list(price_list, currency)

        # 2. POS Profile
        profile = create_pos_profile(
            company=company,
            pos_name=pos_name,
            warehouse=warehouse,
            cashier_emails=cashier_emails,
            price_list=price_list,
            customer=customer_name,
            tax_template=tax_template,
            currency=currency,
        )

        if not profile:
            log("No se pudo crear el POS Profile — revisar errores anteriores", "ERROR")
            return

        # 3. Apertura de caja (opcional)
        if opening_amount > 0 and cashier_emails:
            log(f"Creando apertura de caja con G. {opening_amount:,.0f}...")
            open_shift(
                pos_profile=pos_name,
                cashier_email=cashier_emails[0],
                opening_amount=opening_amount,
            )
        elif opening_amount > 0:
            log("opening_amount > 0 pero no hay cajeros definidos — apertura omitida", "WARN")

        frappe.db.commit()
        print(f"\n{'═' * 56}")
        print(f"  POS configurado exitosamente ✔")
        if opening_amount == 0:
            print(f"  Para abrir caja ejecutar:")
            print(f"    bench execute frappe.setup_pos_profile.open_shift")
            print(f"    --kwargs '{{\"pos_profile\":\"{pos_name}\",")
            print(f"               \"cashier_email\":\"{cashier_emails[0] if cashier_emails else 'email'}\",")
            print(f"               \"opening_amount\":500000}}'")
        print(f"{'═' * 56}\n")

    except Exception as e:
        frappe.db.rollback()
        log(f"ERROR FATAL: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        raise
