"""
setup_roles.py — Matriz de roles, permisos y workspaces por nivel
=================================================================
Crea y sincroniza:
  - Roles personalizados por módulo y nivel
  - Custom DocPerm (permisos por doctype y rol)
  - Workspaces visibles según rol

Uso:
    bench --site erp.chamigo.com.py execute frappe.setup_roles.run

Para solo un módulo:
    bench --site erp.chamigo.com.py execute frappe.setup_roles.run \
        --kwargs '{"modules":["Ventas"]}'
"""

import frappe


# ─────────────────────────────────────────────────────────────────────────────
# MATRIZ CENTRAL — editar aquí para agregar módulos, niveles o permisos
# ─────────────────────────────────────────────────────────────────────────────

MATRIX = {
    "Ventas": {
        "Nivel 1": {
            "role": "Ventas - Nivel 1",
            "description": "Cajero / operador de caja — solo lectura y emisión",
            "docs": {
                "Sales Invoice":  {"read": 1, "print": 1},
                "POS Invoice":    {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1},
                "Item":           {"read": 1},
                "Customer":       {"read": 1},
            },
        },
        "Nivel 2": {
            "role": "Ventas - Nivel 2",
            "description": "Vendedor — puede crear y enviar facturas",
            "docs": {
                "Sales Invoice":  {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1},
                "POS Invoice":    {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "print": 1},
                "Sales Order":    {"read": 1, "write": 1, "create": 1, "submit": 1},
                "Item":           {"read": 1, "write": 1},
                "Item Price":     {"read": 1, "write": 1},
                "Customer":       {"read": 1, "write": 1, "create": 1},
            },
        },
        "Nivel 3": {
            "role": "Ventas - Nivel 3",
            "description": "Supervisor de ventas — puede cancelar y configurar",
            "docs": {
                "Sales Invoice":  {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "delete": 1, "print": 1},
                "POS Invoice":    {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "print": 1},
                "Sales Order":    {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Delivery Note":  {"read": 1, "write": 1, "create": 1, "submit": 1},
                "Item":           {"read": 1, "write": 1, "create": 1},
                "Item Price":     {"read": 1, "write": 1, "create": 1, "delete": 1},
                "Customer":       {"read": 1, "write": 1, "create": 1, "delete": 1},
                "POS Profile":    {"read": 1, "write": 1},
                "Pricing Rule":   {"read": 1, "write": 1, "create": 1},
            },
        },
    },

    "Compras": {
        "Nivel 1": {
            "role": "Compras - Nivel 1",
            "description": "Asistente de compras — solo registro de facturas",
            "docs": {
                "Purchase Invoice": {"read": 1, "create": 1, "write": 1},
                "Supplier":         {"read": 1},
                "Item":             {"read": 1},
            },
        },
        "Nivel 2": {
            "role": "Compras - Nivel 2",
            "description": "Comprador — puede emitir y gestionar órdenes",
            "docs": {
                "Purchase Invoice": {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1},
                "Purchase Order":   {"read": 1, "write": 1, "create": 1, "submit": 1},
                "Supplier":         {"read": 1, "write": 1, "create": 1},
                "Item":             {"read": 1, "write": 1},
            },
        },
        "Nivel 3": {
            "role": "Compras - Nivel 3",
            "description": "Jefe de compras — control total del módulo",
            "docs": {
                "Purchase Invoice": {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "delete": 1, "print": 1},
                "Purchase Order":   {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Supplier":         {"read": 1, "write": 1, "create": 1, "delete": 1},
                "Item":             {"read": 1, "write": 1, "create": 1},
                "Purchase Receipt": {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
            },
        },
    },

    "Stock": {
        "Nivel 1": {
            "role": "Stock - Nivel 1",
            "description": "Auxiliar de almacén — solo consulta",
            "docs": {
                "Item":         {"read": 1},
                "Bin":          {"read": 1},
                "Warehouse":    {"read": 1},
                "Stock Ledger Entry": {"read": 1},
            },
        },
        "Nivel 2": {
            "role": "Stock - Nivel 2",
            "description": "Encargado de almacén — puede registrar movimientos",
            "docs": {
                "Item":          {"read": 1, "write": 1},
                "Bin":           {"read": 1},
                "Warehouse":     {"read": 1},
                "Stock Entry":   {"read": 1, "write": 1, "create": 1, "submit": 1},
                "Stock Ledger Entry": {"read": 1},
            },
        },
        "Nivel 3": {
            "role": "Stock - Nivel 3",
            "description": "Supervisor de almacén — puede cancelar y ajustar",
            "docs": {
                "Item":                  {"read": 1, "write": 1, "create": 1},
                "Bin":                   {"read": 1},
                "Warehouse":             {"read": 1, "write": 1},
                "Stock Entry":           {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Stock Reconciliation":  {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Stock Ledger Entry":    {"read": 1},
                "Item Price":            {"read": 1, "write": 1},
            },
        },
    },

    "Contabilidad": {
        "Nivel 1": {
            "role": "Contabilidad - Nivel 1",
            "description": "Auxiliar contable — solo lectura",
            "docs": {
                "GL Entry":      {"read": 1},
                "Account":       {"read": 1},
                "Journal Entry": {"read": 1, "print": 1},
            },
        },
        "Nivel 2": {
            "role": "Contabilidad - Nivel 2",
            "description": "Contador — puede registrar asientos",
            "docs": {
                "GL Entry":         {"read": 1},
                "Account":          {"read": 1, "write": 1},
                "Journal Entry":    {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1},
                "Payment Entry":    {"read": 1, "write": 1, "create": 1, "submit": 1},
                "Sales Invoice":    {"read": 1},
                "Purchase Invoice": {"read": 1},
            },
        },
        "Nivel 3": {
            "role": "Contabilidad - Nivel 3",
            "description": "Jefe de contabilidad — control total",
            "docs": {
                "GL Entry":         {"read": 1},
                "Account":          {"read": 1, "write": 1, "create": 1},
                "Journal Entry":    {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "print": 1},
                "Payment Entry":    {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Sales Invoice":    {"read": 1, "cancel": 1},
                "Purchase Invoice": {"read": 1, "cancel": 1},
                "Cost Center":      {"read": 1, "write": 1, "create": 1},
            },
        },
    },
}

# Mapeo módulo → nombre de módulo ERPNext para el Workspace
MODULE_MAP = {
    "Ventas":        "Selling",
    "Compras":       "Buying",
    "Stock":         "Stock",
    "Contabilidad":  "Accounts",
}


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def log(msg, level="INFO"):
    prefix = {"INFO": "-", "WARN": "-", "ERROR": "-", "SKIP": "·"}.get(level, " ")
    print(f"  [{level}] {prefix} {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Roles
# ─────────────────────────────────────────────────────────────────────────────

def upsert_role(role_name: str, description: str = "") -> None:
    if frappe.db.exists("Role", role_name):
        log(f"Rol ya existe: {role_name}", "SKIP")
        return

    frappe.get_doc({
        "doctype": "Role",
        "role_name": role_name,
        "desk_access": 1,
        "is_custom": 1,
        "disabled": 0,
    }).insert(ignore_permissions=True)
    log(f"Rol creado: {role_name}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Permisos (Custom DocPerm)
# ─────────────────────────────────────────────────────────────────────────────

_PERM_FIELDS = ["read", "write", "create", "submit", "cancel", "delete", "print",
                "email", "export", "import", "share", "report", "amend"]


def upsert_permission(role: str, doctype: str, perms: dict) -> None:
    """
    Crea o actualiza un Custom DocPerm para el par (role, doctype).

    Custom DocPerm es un DocType de Frappe (no una tabla directa).
    El campo `parent` es el nombre del DocType al que aplica el permiso.
    parenttype siempre es "DocType".
    """
    # Verificar que el doctype existe en esta instalación
    if not frappe.db.exists("DocType", doctype):
        log(f"DocType no encontrado, skip: {doctype}", "WARN")
        return

    existing = frappe.db.get_value(
        "Custom DocPerm",
        {"role": role, "parent": doctype, "permlevel": 0},
        "name",
    )

    payload = {field: perms.get(field, 0) for field in _PERM_FIELDS}

    if not existing:
        doc = frappe.get_doc({
            "doctype":    "Custom DocPerm",
            "parent":     doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role":       role,
            "permlevel":  0,
            **payload,
        })
        doc.insert(ignore_permissions=True)
        log(f"Permiso creado: [{role}] → {doctype}")
        return

    # Actualizar solo si hay diferencias
    doc = frappe.get_doc("Custom DocPerm", existing)
    changed = False
    for field, val in payload.items():
        current = int(doc.get(field) or 0)
        if current != val:
            doc.set(field, val)
            changed = True

    if changed:
        doc.save(ignore_permissions=True)
        log(f"Permiso actualizado: [{role}] → {doctype}")
    else:
        log(f"Permiso sin cambios: [{role}] → {doctype}", "SKIP")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Workspaces
# ─────────────────────────────────────────────────────────────────────────────

def upsert_workspace(ws_name: str, module: str, role: str) -> None:
    """
    Crea o actualiza un Workspace personalizado visible solo para el rol dado.

    En ERPNext v16 los Workspaces tienen una tabla hija `for_roles`.
    Si el workspace ya existe, agrega el rol si no está registrado.
    """
    if not frappe.db.exists("Workspace", ws_name):
        try:
            ws = frappe.get_doc({
                "doctype":     "Workspace",
                "name":        ws_name,   # requerido en ERPNext v16
                "title":       ws_name,
                "module":      module,
                "is_standard": 0,
                "public":      0,
                "for_roles":   [{"role": role}],
                "content":     "[]",
                "charts":      [],
                "shortcuts":   [],
                "links":       [],
            })
            ws.flags.ignore_mandatory = True
            ws.insert(ignore_permissions=True)
            log(f"Workspace creado: {ws_name}")
        except Exception as e:
            log(f"Error al crear workspace {ws_name}: {e}", "WARN")
        return

    ws = frappe.get_doc("Workspace", ws_name)
    existing_roles = [r.role for r in (ws.for_roles or [])]

    if role not in existing_roles:
        ws.append("for_roles", {"role": role})
        ws.save(ignore_permissions=True)
        log(f"Workspace actualizado con rol [{role}]: {ws_name}")
    else:
        log(f"Workspace sin cambios: {ws_name}", "SKIP")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Role Profile (agrupa roles para asignación masiva a usuarios)
# ─────────────────────────────────────────────────────────────────────────────

def upsert_role_profile(profile_name: str, roles: list[str]) -> None:
    """
    Un Role Profile agrupa varios roles en un perfil reutilizable.
    Se asigna en tabUser.role_profile_name en lugar de agregar roles uno a uno.
    """
    if frappe.db.exists("Role Profile", profile_name):
        log(f"Role Profile ya existe: {profile_name}", "SKIP")
        return

    doc = frappe.get_doc({
        "doctype": "Role Profile",
        "role_profile": profile_name,
        "roles": [{"role": r} for r in roles if frappe.db.exists("Role", r)],
    })
    doc.insert(ignore_permissions=True)
    log(f"Role Profile creado: {profile_name} ({len(doc.roles)} roles)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Asignar rol a usuario
# ─────────────────────────────────────────────────────────────────────────────

def assign_role_to_user(email: str, role: str) -> None:
    """
    Agrega un rol a un usuario existente si no lo tiene ya.
    """
    if not frappe.db.exists("User", email):
        log(f"Usuario no encontrado: {email}", "WARN")
        return

    doc = frappe.get_doc("User", email)
    existing = [r.role for r in doc.roles]

    if role in existing:
        log(f"Usuario {email} ya tiene el rol {role}", "SKIP")
        return

    doc.append("roles", {"role": role})
    doc.save(ignore_permissions=True)
    log(f"Rol [{role}] asignado a {email}")


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada principal
# ─────────────────────────────────────────────────────────────────────────────

def run(modules: list = None) -> None:
    """
    Sincroniza roles, permisos y workspaces según la MATRIX.

    Args:
        modules: Lista de módulos a procesar. None = todos.
                 Ej: ["Ventas", "Stock"]

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_roles.run

        # Solo Ventas y Stock:
        bench --site erp.chamigo.com.py execute frappe.setup_roles.run \
            --kwargs '{"modules":["Ventas","Stock"]}'
    """
    frappe.set_user("Administrator")

    target = {k: v for k, v in MATRIX.items() if modules is None or k in modules}

    print(f"\n{'═' * 56}")
    print(f"  Sincronizando {len(target)} módulos: {list(target.keys())}")
    print(f"{'═' * 56}\n")

    try:
        roles_created = []

        for modulo, niveles in target.items():
            print(f"\n── {modulo} ──────────────────────────────────────")
            module_name = MODULE_MAP.get(modulo, modulo)

            for nivel, config in niveles.items():
                role = config["role"]
                desc = config.get("description", "")
                print(f"\n  {nivel}: {role}")

                # 1. Rol
                upsert_role(role, desc)
                roles_created.append(role)

                # 2. Permisos por doctype
                for doctype, perms in config["docs"].items():
                    upsert_permission(role, doctype, perms)

                # 3. Workspace
                ws_name = config.get("workspace", f"{modulo} - {nivel}")
                upsert_workspace(ws_name, module_name, role)

        # 4. Role Profiles (un perfil por nivel que agrupa todos los módulos)
        print(f"\n── Role Profiles ──────────────────────────────────")
        for nivel_num in range(1, 4):
            nivel_key = f"Nivel {nivel_num}"
            perfil_roles = [
                cfg[nivel_key]["role"]
                for cfg in target.values()
                if nivel_key in cfg
            ]
            if perfil_roles:
                upsert_role_profile(f"Perfil - {nivel_key}", perfil_roles)

        # 5. Aplicar permisos en el cache de Frappe
        frappe.db.commit()
        frappe.clear_cache()

        # reload_doc para que los Custom DocPerm surtan efecto inmediato
        for modulo, niveles in target.items():
            for nivel, config in niveles.items():
                for doctype in config["docs"]:
                    if frappe.db.exists("DocType", doctype):
                        try:
                            frappe.reload_doc(
                                frappe.db.get_value("DocType", doctype, "module"),
                                "doctype",
                                frappe.scrub(doctype),
                            )
                        except Exception:
                            pass

        frappe.clear_cache()
        frappe.db.commit()

        print(f"\n{'═' * 56}")
        print(f"  SYNC COMPLETO ")
        print(f"  Roles procesados: {len(set(roles_created))}")
        print(f"{'═' * 56}\n")

    except Exception as e:
        frappe.db.rollback()
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Utilidad: asignar perfil a usuario
# ─────────────────────────────────────────────────────────────────────────────

def assign_profile(email: str, profile_name: str) -> None:
    """
    Asigna un Role Profile a un usuario. Más limpio que asignar roles uno a uno.

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_roles.assign_profile \
            --kwargs '{"email":"ventas@chamigo.com.py","profile_name":"Perfil - Nivel 1"}'
    """
    frappe.set_user("Administrator")

    if not frappe.db.exists("User", email):
        print(f"[ERROR] Usuario no encontrado: {email}")
        return
    if not frappe.db.exists("Role Profile", profile_name):
        print(f"[ERROR] Role Profile no encontrado: {profile_name}")
        return

    doc = frappe.get_doc("User", email)
    doc.role_profile_name = profile_name
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"[INFO] Perfil [{profile_name}] asignado a {email}")
