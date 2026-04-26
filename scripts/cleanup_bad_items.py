"""
cleanup_bad_items.py — Elimina items creados con nombre en notación científica
===============================================================================
Cuando Excel abre un CSV y convierte barcodes EAN-13 a notación científica
(ej: 7840994000142 → 7.84001E+12), ERPNext los guarda con ese nombre corrupto.
Este script los detecta y elimina para poder reimportarlos correctamente.

Uso:
    bench --site erp.chamigo.com.py execute frappe.cleanup_bad_items.run
"""
import re, frappe


def log(msg, level="INFO"):
    prefix = {"INFO": "✔", "WARN": "⚠", "ERROR": "✖"}.get(level, "·")
    print(f"[{level}] {prefix} {msg}", flush=True)


def is_scientific(name):
    """Detecta si un nombre de item está en notación científica de Excel."""
    return bool(re.match(r'^\d+\.\d+E\+\d+$', str(name).strip(), re.IGNORECASE))


def run(dry_run: bool = False):
    """
    Detecta y elimina items con nombre en notación científica.

    Args:
        dry_run: Si True, solo muestra qué se eliminaría sin borrar nada.

    Uso:
        # Ver qué se va a eliminar (sin borrar)
        bench --site erp.chamigo.com.py execute frappe.cleanup_bad_items.run \
            --kwargs '{"dry_run":True}'

        # Eliminar
        bench --site erp.chamigo.com.py execute frappe.cleanup_bad_items.run
    """
    frappe.set_user("Administrator")

    all_items = frappe.get_all("Item", pluck="name")
    bad = [n for n in all_items if is_scientific(n)]

    log(f"Items totales: {len(all_items)}")
    log(f"Items con nombre corrupto (notacion cientifica): {len(bad)}")

    if not bad:
        log("Nada que limpiar.")
        return

    for name in bad:
        item_name = frappe.db.get_value("Item", name, "item_name")
        log(f"{'[DRY] ' if dry_run else ''}Eliminando: {name} | {item_name}")

        if not dry_run:
            # Eliminar primero los registros hijos
            for child in ["Item Default", "Item Barcode", "Item Price",
                          "Item Supplier", "Item Customer Detail",
                          "Item Reorder", "Item Tax", "UOM Conversion Detail"]:
                for row in frappe.get_all(child, filters={"parent": name}, pluck="name"):
                    frappe.delete_doc(child, row, force=1, ignore_permissions=True)

            # Eliminar precios
            for ip in frappe.get_all("Item Price", filters={"item_code": name}, pluck="name"):
                frappe.delete_doc("Item Price", ip, force=1, ignore_permissions=True)

            frappe.delete_doc("Item", name, force=1, ignore_permissions=True)

    if not dry_run:
        frappe.db.commit()
        log(f"Eliminados {len(bad)} items corruptos. Ahora reimportar con load_catalog.run.")
    else:
        log(f"[DRY RUN] Se eliminarían {len(bad)} items. Ejecutar sin dry_run=True para confirmar.")
