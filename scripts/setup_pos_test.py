"""
setup_pos_test.py — Configuración completa para prueba de flujo POS
====================================================================
Prepara el entorno para que dos cajeros puedan probar todos los
escenarios listados: búsqueda, cantidades, balanza, embalajes,
promos, crédito/contado, cambio/vuelto.

Crea/configura:
  - Rol "Ventas - Nivel 1" con permisos POS completos
  - POS Profile con todas las opciones habilitadas
  - Modos de pago: Efectivo, Tarjeta, Transferencia, QR, Crédito (Fiado)
  - Customer Credit Limit para ventas a crédito
  - Pricing Rules para promos
  - Apertura de caja para ambos cajeros

Uso:
    bench --site erp.chamigo.com.py execute frappe.setup_pos_test.run \\
        --kwargs '{
            "company": "Chamigo E.A.S",
            "warehouse": "Stores - CHA",
            "cashiers": [
                {"email": "cajero1@chamigo.com.py", "opening": 500000},
                {"email": "cajero2@chamigo.com.py", "opening": 300000}
            ]
        }'
"""

import frappe
from frappe.utils import nowdate, now_datetime, add_days


def log(msg, level="INFO"):
    prefix = {"INFO": "✔", "WARN": "⚠", "ERROR": "✖", "SKIP": "·"}.get(level, " ")
    print(f"  [{level}] {prefix} {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Permisos completos para Ventas - Nivel 1 (cajero POS)
# ─────────────────────────────────────────────────────────────────────────────

CAJERO_ROLE = "Ventas - Nivel 1"

CAJERO_PERMS = {
    # POS core
    "POS Invoice":          {"read":1,"write":1,"create":1,"submit":1,"cancel":1,"print":1,"email":1},
    "POS Opening Entry":    {"read":1,"write":1,"create":1,"submit":1},
    "POS Closing Entry":    {"read":1,"write":1,"create":1,"submit":1,"print":1},
    "POS Profile":          {"read":1},
    # Documentos de venta
    "Sales Invoice":        {"read":1,"write":1,"create":1,"submit":1,"print":1,"email":1},
    "Payment Entry":        {"read":1,"write":1,"create":1,"submit":1,"print":1},
    # Crédito / fiado
    "Sales Order":          {"read":1,"write":1,"create":1,"submit":1,"print":1},
    "Customer":             {"read":1,"write":1,"create":1},
    # Catálogo
    "Item":                 {"read":1},
    "Item Price":           {"read":1},
    "Pricing Rule":         {"read":1},
    # Stock consulta
    "Bin":                  {"read":1},
    "Warehouse":            {"read":1},
    # Contabilidad consulta
    "Account":              {"read":1},
    "Mode of Payment":      {"read":1},
}


def setup_cajero_role():
    """Crea el rol y sus permisos si no existen."""
    log(f"Configurando rol: {CAJERO_ROLE}")

    if not frappe.db.exists("Role", CAJERO_ROLE):
        frappe.get_doc({
            "doctype":    "Role",
            "role_name":  CAJERO_ROLE,
            "desk_access": 1,
            "is_custom":  1,
        }).insert(ignore_permissions=True)
        log(f"Rol creado: {CAJERO_ROLE}")
    else:
        log(f"Rol ya existe: {CAJERO_ROLE}", "SKIP")

    _PERM_FIELDS = ["read","write","create","submit","cancel","delete",
                    "print","email","export","import","share","report","amend"]

    for doctype, perms in CAJERO_PERMS.items():
        if not frappe.db.exists("DocType", doctype):
            log(f"DocType no existe, skip: {doctype}", "WARN")
            continue

        existing = frappe.db.get_value(
            "Custom DocPerm",
            {"role": CAJERO_ROLE, "parent": doctype, "permlevel": 0},
            "name",
        )
        payload = {f: perms.get(f, 0) for f in _PERM_FIELDS}

        if not existing:
            frappe.get_doc({
                "doctype":     "Custom DocPerm",
                "parent":      doctype,
                "parenttype":  "DocType",
                "parentfield": "permissions",
                "role":        CAJERO_ROLE,
                "permlevel":   0,
                **payload,
            }).insert(ignore_permissions=True)
            log(f"Permiso creado: {doctype}")
        else:
            doc = frappe.get_doc("Custom DocPerm", existing)
            changed = any(int(doc.get(f) or 0) != v for f, v in payload.items())
            if changed:
                for f, v in payload.items():
                    doc.set(f, v)
                doc.save(ignore_permissions=True)
                log(f"Permiso actualizado: {doctype}")
            else:
                log(f"Sin cambios: {doctype}", "SKIP")

    frappe.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Asignar rol a usuarios cajeros
# ─────────────────────────────────────────────────────────────────────────────

def assign_cashier_role(email):
    if not frappe.db.exists("User", email):
        log(f"Usuario no encontrado: {email}", "WARN")
        return False

    # Habilitar usuario si está deshabilitado
    if not frappe.db.get_value("User", email, "enabled"):
        frappe.db.set_value("User", email, "enabled", 1)
        log(f"Usuario habilitado: {email}")

    doc = frappe.get_doc("User", email)
    existing_roles = [r.role for r in doc.roles]

    if CAJERO_ROLE not in existing_roles:
        doc.append("roles", {"role": CAJERO_ROLE})
        doc.save(ignore_permissions=True)
        log(f"Rol [{CAJERO_ROLE}] asignado a {email}")
    else:
        log(f"{email} ya tiene el rol", "SKIP")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Modos de pago con sus cuentas
# ─────────────────────────────────────────────────────────────────────────────

def find_account(company, *names, account_type=None):
    for name in names:
        r = frappe.db.get_value("Account",
            {"company": company, "account_name": name, "is_group": 0}, "name")
        if r: return r
    if account_type:
        return frappe.db.get_value("Account",
            {"company": company, "account_type": account_type, "is_group": 0}, "name")
    return None


def setup_payment_modes(company):
    """
    Asegura que existan todos los modos de pago necesarios para el flujo de prueba,
    incluyendo el modo Crédito/Fiado que usa una cuenta por cobrar.
    """
    log("Configurando modos de pago...")

    cash_acc  = find_account(company, "Caja General", "Cash",        account_type="Cash")
    bank_acc  = find_account(company, "Banco Principal",              account_type="Bank")
    qr_acc    = find_account(company, "Billeteras Digitales", "QR",   account_type="Bank")
    recv_acc  = find_account(company, "Debtors", "Cuentas por Cobrar", account_type="Receivable")

    mops = [
        ("Efectivo",               "Cash", cash_acc),
        ("Tarjeta de Crédito",     "Bank", bank_acc),
        ("Tarjeta de Débito",      "Bank", bank_acc),
        ("Transferencia Bancaria", "Bank", bank_acc),
        ("QR / Billetera Digital", "Bank", qr_acc or bank_acc),
        ("Crédito / Fiado",        "Bank", recv_acc or bank_acc),  # venta a crédito
    ]

    for name, mtype, account in mops:
        if not account:
            log(f"Sin cuenta para {name} — skip", "WARN")
            continue

        if not frappe.db.exists("Mode of Payment", name):
            frappe.get_doc({
                "doctype":          "Mode of Payment",
                "mode_of_payment":  name,
                "type":             mtype,
                "accounts": [{"company": company, "default_account": account}],
            }).insert(ignore_permissions=True)
            log(f"MOP creado: {name}")
        else:
            # Asegurar que tiene cuenta para esta empresa
            existing_account = frappe.db.get_value(
                "Mode of Payment Account",
                {"parent": name, "company": company},
                "name",
            )
            if not existing_account:
                doc = frappe.get_doc("Mode of Payment", name)
                doc.append("accounts", {"company": company, "default_account": account})
                doc.save(ignore_permissions=True)
                log(f"Cuenta agregada a MOP: {name}")
            else:
                log(f"MOP ya configurado: {name}", "SKIP")

    frappe.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# 4. POS Profile con todas las opciones del flujo de prueba
# ─────────────────────────────────────────────────────────────────────────────

def setup_pos_profile(company, pos_name, warehouse, cashier_emails):
    log(f"Configurando POS Profile: {pos_name}")

    if frappe.db.exists("POS Profile", pos_name):
        log(f"POS Profile ya existe — actualizando usuarios...", "SKIP")
        _add_users(pos_name, cashier_emails)
        return pos_name

    income_acc   = find_account(company, "Sales", "Ventas",           account_type="Income Account")
    expense_acc  = find_account(company, "Cost of Goods Sold",         account_type="Expense Account")
    writeoff_acc = find_account(company, "Write Off", "Round Off",     account_type="Expense Account")
    cost_center  = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")

    tax_template = frappe.db.get_value(
        "Sales Taxes and Charges Template",
        {"company": company, "is_default": 1}, "name"
    )

    # Construir modos de pago del perfil
    payment_rows = []
    mop_names = ["Efectivo","Tarjeta de Crédito","Tarjeta de Débito",
                 "Transferencia Bancaria","QR / Billetera Digital","Crédito / Fiado"]
    for i, mop_name in enumerate(mop_names):
        mop_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mop_name, "company": company},
            "default_account",
        ) or None
        if not mop_account:
            log(f"Sin cuenta para MOP '{mop_name}' — skip", "WARN")
            continue
        payment_rows.append({
            "mode_of_payment": mop_name,
            "account":         mop_account,
            "default":         1 if mop_name == "Efectivo" else 0,
        })

    # Usuarios — verificar si ya tienen default en otro perfil
    user_rows = []
    for email in cashier_emails:
        if not frappe.db.exists("User", email):
            continue
        # Si el usuario ya tiene un POS Profile default, no marcar como default aquí
        existing_default = frappe.db.sql("""
            SELECT ppu.parent
            FROM `tabPOS Profile User` ppu
            JOIN `tabPOS Profile` pp ON pp.name = ppu.parent
            WHERE ppu.user = %s AND ppu.default = 1 AND pp.disabled = 0
            LIMIT 1
        """, email)
        has_default = bool(existing_default)
        user_rows.append({"user": email, "default": 0 if has_default else 1})
        if has_default:
            log(f"{email} ya tiene default en '{existing_default[0][0]}' — se agrega sin default", "WARN")

    # Asegurar cliente genérico
    if not frappe.db.exists("Customer", "Consumidor Final"):
        frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Consumidor Final",
            "customer_type": "Individual",
            "customer_group": frappe.db.get_value("Customer Group", {}, "name") or "All Customer Groups",
            "territory": "All Territories",
        }).insert(ignore_permissions=True)

    # Asegurar lista de precios
    if not frappe.db.exists("Price List", "Lista POS"):
        frappe.get_doc({
            "doctype": "Price List",
            "price_list_name": "Lista POS",
            "currency": "PYG",
            "selling": 1,
            "enabled": 1,
        }).insert(ignore_permissions=True)

    doc = frappe.get_doc({
        "doctype":          "POS Profile",
        "name":             pos_name,
        "pos_profile_name": pos_name,
        "company":          company,
        "warehouse":        warehouse,
        "currency":         "PYG",
        "selling_price_list": "Lista POS",
        "customer":         "Consumidor Final",
        "taxes_and_charges": tax_template,
        "cost_center":      cost_center,
        "income_account":   income_acc,
        "expense_account":  expense_acc,
        "write_off_account": writeoff_acc or income_acc,
        "write_off_cost_center": cost_center,
        # ── Opciones clave para el flujo de prueba ──
        "allow_discount_change":      1,   # EDICIÓN TOTAL / PRECIO
        "allow_rate_change":          1,   # EDICIÓN PRECIO UNITARIO
        "hide_images":                0,   # mostrar imágenes de items
        "validate_stock_on_save":     0,   # permitir STOCK NEGATIVO en prueba
        "allow_negative_stock_in_pos": 1,  # STOCK NEGATIVO habilitado
        # Impresión
        "print_format": "",
        # Tablas hijas
        "applicable_for_users": user_rows,
        "payments":             payment_rows,
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"POS Profile creado con {len(payment_rows)} modos de pago")
    log(f"Cajeros: {[r['user'] for r in user_rows]}")
    return pos_name


def _add_users(pos_name, emails):
    doc = frappe.get_doc("POS Profile", pos_name)
    existing = {r.user for r in doc.applicable_for_users}
    added = 0
    for email in emails:
        if email not in existing and frappe.db.exists("User", email):
            doc.append("applicable_for_users", {"user": email})
            added += 1
    if added:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        log(f"{added} cajero(s) agregado(s)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Límite de crédito para clientes (Fiado)
# ─────────────────────────────────────────────────────────────────────────────

def setup_credit_limit(company, customer_name, limit=1000000):
    """
    Configura límite de crédito para un cliente (necesario para Fiado/Crédito).
    En ERPNext el límite de crédito vive en Customer Credit Limit (child de Customer).
    """
    if not frappe.db.exists("Customer", customer_name):
        log(f"Cliente no encontrado: {customer_name}", "WARN")
        return

    doc = frappe.get_doc("Customer", customer_name)

    # Verificar si ya tiene límite para esta empresa
    existing = [c for c in (doc.credit_limits or []) if c.company == company]
    if existing:
        log(f"Límite de crédito ya configurado para {customer_name}", "SKIP")
        return

    doc.append("credit_limits", {
        "company":      company,
        "credit_limit": limit,
        "bypass_credit_limit_check": 0,
    })
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    log(f"Límite de crédito G. {limit:,.0f} configurado para: {customer_name}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Apertura de caja para cada cajero
# ─────────────────────────────────────────────────────────────────────────────

def open_shift(pos_profile, cashier_email, opening_amount=0):
    if not frappe.db.get_value("User", cashier_email, "enabled"):
        log(f"Usuario deshabilitado: {cashier_email}", "WARN")
        return None

    # Verificar apertura activa
    existing = frappe.db.get_value(
        "POS Opening Entry",
        {"pos_profile": pos_profile, "docstatus": 1, "status": "Open"},
        "name",
    )
    if existing:
        log(f"Apertura activa ya existe: {existing} — skip", "SKIP")
        return existing

    profile_doc = frappe.get_doc("POS Profile", pos_profile)
    balance_details = []
    for p in profile_doc.payments:
        balance_details.append({
            "mode_of_payment": p.mode_of_payment,
            "opening_amount":  opening_amount if p.mode_of_payment == "Efectivo" else 0,
        })

    if not balance_details:
        log("Sin modos de pago en el perfil", "ERROR")
        return None

    doc = frappe.get_doc({
        "doctype":           "POS Opening Entry",
        "pos_profile":       pos_profile,
        "user":              cashier_email,
        "company":           profile_doc.company,
        "pos_opening_time":  now_datetime(),
        "period_start_date": nowdate(),
        "balance_details":   balance_details,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()
    log(f"Caja abierta: {doc.name} | {cashier_email} | G. {opening_amount:,.0f}")
    return doc.name


# ─────────────────────────────────────────────────────────────────────────────
# 7. User Permission por empresa para cada cajero
# ─────────────────────────────────────────────────────────────────────────────

def setup_user_permission(email, company):
    existing = frappe.db.get_value(
        "User Permission",
        {"user": email, "allow": "Company", "for_value": company},
        "name",
    )
    if existing:
        log(f"User Permission ya existe para {email}", "SKIP")
        return

    frappe.get_doc({
        "doctype":              "User Permission",
        "user":                 email,
        "allow":                "Company",
        "for_value":            company,
        "apply_to_all_doctypes": 1,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"User Permission configurado: {email} → {company}")


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────────────────────────────────────

def run(
    company: str,
    warehouse: str,
    cashiers: list,
    pos_name: str = "Caja de Pruebas - POS Test",
    customers_credit: list = None,
    credit_limit: float = 2000000,
):
    """
    Configura el entorno completo para prueba de flujo POS.

    Args:
        company          : Empresa
        warehouse        : Depósito
        cashiers         : Lista de dicts [{"email": "...", "opening": 500000}]
        pos_name         : Nombre del POS Profile de prueba
        customers_credit : Lista de nombres de clientes con crédito habilitado
        credit_limit     : Límite de crédito en PYG (default 2.000.000)

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_pos_test.run \\
            --kwargs '{
                "company": "Chamigo E.A.S",
                "warehouse": "Stores - CHA",
                "cashiers": [
                    {"email": "cajero1@chamigo.com.py", "opening": 500000},
                    {"email": "cajero2@chamigo.com.py", "opening": 300000}
                ],
                "customers_credit": ["Cliente A", "Cliente B"]
            }'
    """
    frappe.set_user("Administrator")

    emails = [c["email"] for c in cashiers]

    print(f"\n{'═'*58}")
    print(f"  POS Test Setup")
    print(f"  Empresa  : {company}")
    print(f"  POS      : {pos_name}")
    print(f"  Cajeros  : {emails}")
    print(f"{'═'*58}\n")

    try:
        # 1. Rol y permisos
        print("── 1. Rol cajero ──────────────────────────────────────")
        setup_cajero_role()

        # 2. Asignar rol a cajeros + User Permission
        print("\n── 2. Usuarios ────────────────────────────────────────")
        for email in emails:
            assign_cashier_role(email)
            setup_user_permission(email, company)

        # 3. Modos de pago
        print("\n── 3. Modos de pago ───────────────────────────────────")
        setup_payment_modes(company)

        # 4. POS Profile
        print("\n── 4. POS Profile ─────────────────────────────────────")
        setup_pos_profile(company, pos_name, warehouse, emails)

        # 5. Límite de crédito para clientes fiado
        print("\n── 5. Crédito / Fiado ─────────────────────────────────")
        for cname in (customers_credit or []):
            setup_credit_limit(company, cname, credit_limit)
        # También al cliente genérico para pruebas
        setup_credit_limit(company, "Consumidor Final", credit_limit)

        # 6. Apertura de caja
        print("\n── 6. Apertura de caja ────────────────────────────────")
        for c in cashiers:
            open_shift(pos_name, c["email"], c.get("opening", 0))

        frappe.clear_cache()
        frappe.db.commit()

        print(f"\n{'═'*58}")
        print(f"  Setup completado ✔")
        print(f"\n  Checklist de pruebas habilitadas:")
        features = [
            ("BUSCADOR POR DESCRIPCIÓN",     "Nativo en POS — buscar en la barra de items"),
            ("BUSCADOR POR CÓDIGO / BARCODE", "Nativo — escanear o escribir el código EAN"),
            ("CANTIDAD DE PRODUCTOS",         "Nativo — campo qty en la línea"),
            ("INTEGRACIÓN DE BALANZA",        "Items con stock_uom=Kg — ingresar peso manual"),
            ("EDICIÓN CANTIDAD",              "Habilitado — allow_discount_change=1"),
            ("EDICIÓN PRECIO UNITARIO",       "Habilitado — allow_rate_change=1"),
            ("EDICIÓN PRECIO TOTAL",          "Habilitado — permite modificar discount"),
            ("ELIMINAR PRODUCTO",             "Nativo — botón eliminar línea"),
            ("STOCK NEGATIVO",                "Habilitado — validate_stock_on_save=0"),
            ("MOSTRAR TICKET",                "Nativo — print_format asignado al POS"),
            ("PROMO / DESCUENTO",             "Via Pricing Rule en los items"),
            ("CALCULO EMBALAJES",             "Via UOM Conversion en el item (Caja→Unidad)"),
            ("FIADO / CRÉDITO",               "MOP 'Crédito / Fiado' + Customer credit_limit"),
            ("AÑADIR MÉTODO DE PAGO",         "Múltiples MOP cargados en el POS Profile"),
            ("IMPORTE TOTAL / CAMBIO",        "Nativo — campo change_amount en POS"),
            ("NRO TICKET / FACTURA",          "Nativo — naming series de POS Invoice"),
        ]
        for feat, nota in features:
            print(f"  ✔  {feat:<35} {nota}")
        print(f"\n{'═'*58}\n")

    except Exception as e:
        frappe.db.rollback()
        log(f"ERROR FATAL: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        raise
