import frappe
import json

# -----------------------------
# MATRIZ CENTRAL
# -----------------------------
MATRIX = {
    # -------------------------
    # SELLING (VENTAS)
    # -------------------------
    "Ventas": {
        "Nivel 1": {
            "role": "Ventas - Nivel 1",
            "workspace": "Ventas - Nivel 1",
            "docs": {
                "Sales Invoice": {"read": 1, "print": 1},
                "Item": {"read": 1}
            }
        },
        "Nivel 2": {
            "role": "Ventas - Nivel 2",
            "workspace": "Ventas - Nivel 2",
            "docs": {
                "Sales Invoice": {"read": 1, "write": 1, "submit": 1},
                "Item": {"read": 1, "write": 1},
                "Item Price": {"read": 1, "write": 1},
                "Sales Order": {"read": 1, "write": 1}
            }
        },
        "Nivel 3": {
            "role": "Ventas - Nivel 3",
            "workspace": "Ventas - Nivel 3",
            "docs": {
                "Sales Invoice": {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Item": {"read": 1, "write": 1},
                "Item Price": {"read": 1, "write": 1},
                "Sales Order": {"read": 1, "write": 1, "submit": 1, "cancel": 1},
                "Delivery Note": {"read": 1, "write": 1}
            }
        }
    },

    # -------------------------
    # BUYING (COMPRAS)
    # -------------------------
    "Compras": {
        "Nivel 1": {
            "role": "Compras - Nivel 1",
            "workspace": "Compras - Nivel 1",
            "docs": {
                "Purchase Invoice": {"read": 1, "create": 1},
                "Supplier": {"read": 1}
            }
        },
        "Nivel 2": {
            "role": "Compras - Nivel 2",
            "workspace": "Compras - Nivel 2",
            "docs": {
                "Purchase Invoice": {"read": 1, "write": 1, "submit": 1},
                "Purchase Order": {"read": 1, "write": 1},
                "Supplier": {"read": 1, "write": 1}
            }
        },
        "Nivel 3": {
            "role": "Compras - Nivel 3",
            "workspace": "Compras - Nivel 3",
            "docs": {
                "Purchase Invoice": {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Purchase Order": {"read": 1, "write": 1, "submit": 1, "cancel": 1},
                "Supplier": {"read": 1, "write": 1}
            }
        }
    },

    # -------------------------
    # STOCK (INVENTARIO)
    # -------------------------
    "Stock": {
        "Nivel 1": {
            "role": "Stock - Nivel 1",
            "workspace": "Stock - Nivel 1",
            "docs": {
                "Item": {"read": 1},
                "Bin": {"read": 1}
            }
        },
        "Nivel 2": {
            "role": "Stock - Nivel 2",
            "workspace": "Stock - Nivel 2",
            "docs": {
                "Item": {"read": 1, "write": 1},
                "Stock Entry": {"read": 1, "create": 1, "write": 1},
                "Warehouse": {"read": 1}
            }
        },
        "Nivel 3": {
            "role": "Stock - Nivel 3",
            "workspace": "Stock - Nivel 3",
            "docs": {
                "Item": {"read": 1, "write": 1},
                "Stock Entry": {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
                "Warehouse": {"read": 1, "write": 1},
                "Stock Reconciliation": {"read": 1, "write": 1, "submit": 1}
            }
        }
    }
}

MODULE_MAP = {
    "Ventas": "Selling",
    "Compras": "Buying",
    "Stock": "Stock"
}


# -----------------------------
# 1. ROLES (UPSERT)
# -----------------------------
def upsert_role(role_name):
    role = frappe.db.exists("Role", role_name)

    if not role:
        frappe.get_doc({
            "doctype": "Role",
            "role_name": role_name
        }).insert(ignore_permissions=True)
        print(f"Rol creado: {role_name}")
    else:
        print(f"Rol existe: {role_name} (no changes)")

# -----------------------------
# 2. PERMISOS (UPSERT INTELIGENTE)
# -----------------------------
def upsert_permission(role, doctype, perms):
    existing = frappe.db.exists("Custom DocPerm", {
        "role": role,
        "parent": doctype,
        "permlevel": 0
    })

    payload = {
        "read": perms.get("read", 0),
        "write": perms.get("write", 0),
        "create": perms.get("create", 0),
        "submit": perms.get("submit", 0),
        "cancel": perms.get("cancel", 0),
        "delete": perms.get("delete", 0),
        "print": perms.get("print", 0)
    }

    if not existing:
        doc = frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "role": role,
            "permlevel": 0,
            **payload
        })
        doc.insert(ignore_permissions=True)
        print(f"✔ Permiso creado: {role} → {doctype}")

    else:
        doc = frappe.get_doc("Custom DocPerm", existing)

        changed = False
        for k, v in payload.items():
            if getattr(doc, k) != v:
                setattr(doc, k, v)
                changed = True

        if changed:
            doc.save(ignore_permissions=True)
            print(f" Permiso actualizado: {role} → {doctype}")
        else:
            print(f" Permiso sin cambios: {role} → {doctype}")

# -----------------------------
# 3. WORKSPACE (UPSERT)
# -----------------------------
def upsert_workspace(name, module, role):
    existing = frappe.db.exists("Workspace", name)

    if not existing:
        ws = frappe.get_doc({
            "doctype": "Workspace",
            "title": name,
            "module": module,
            "is_standard": 0,
            "for_roles": [{"role": role}],
            "content": "[]"
        })
        ws.insert(ignore_permissions=True)
        print(f" Workspace creado: {name}")

    else:
        ws = frappe.get_doc("Workspace", name)

        # actualizar roles si cambian
        roles_existing = [r.role for r in ws.for_roles]

        if role not in roles_existing:
            ws.append("for_roles", {"role": role})
            ws.save(ignore_permissions=True)
            print(f" Workspace actualizado (roles): {name}")
        else:
            print(f" Workspace sin cambios: {name}")

# -----------------------------
# 4. SYNC GENERAL
# -----------------------------
def run():
    try:
        frappe.db.begin()

        for module, levels in MATRIX.items():
            for lvl, config in levels.items():

                role = config["role"]
                ws = config["workspace"]

                # ROLES
                upsert_role(role)

                # PERMISOS
                for doctype, perms in config["docs"].items():
                    upsert_permission(role, doctype, perms)

                # WORKSPACES
                module_name = MODULE_MAP[module]
                upsert_workspace(ws, module_name, role)

        frappe.clear_cache()
        frappe.db.commit()

        print(" SYNC COMPLETO (roles + permisos + UI)")

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "SYNC ERROR")

        print(" ERROR - rollback ejecutado")
        print(str(e))
