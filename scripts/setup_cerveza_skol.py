"""
setup_skol_lata.py — Skol Lata 269ml con presentación unitaria y pack x15
"""
import frappe
from frappe.utils import nowdate

ITEM_CODE  = "7891149103102"
ITEM_NAME  = "Skol Lata 269ml"
ITEM_GROUP = "Cerveza"
STOCK_UOM  = "UNI"
PRICE_LIST = "Lista POS"

PRESENTATIONS = [
    ("UNI",      1,  "7891149103102", 4000),
    ("Pack x15", 15, "7840050009157", 57000),
]


def log(msg, level="INFO"):
    prefix = {"INFO": "✔", "WARN": "⚠", "ERROR": "✖", "SKIP": "·"}.get(level, " ")
    print(f"  [{level}] {prefix} {msg}", flush=True)


def _ensure_uom(name):
    if not frappe.db.exists("UOM", name):
        frappe.get_doc({"doctype": "UOM", "uom_name": name,
                        "enabled": 1, "must_be_whole_number": 1}).insert(ignore_permissions=True)
        log(f"UOM creada: {name}")


def _upsert_price(uom, precio):
    if not frappe.db.exists("Price List", PRICE_LIST):
        frappe.get_doc({"doctype": "Price List", "price_list_name": PRICE_LIST,
                        "currency": "PYG", "selling": 1, "enabled": 1}).insert(ignore_permissions=True)
    existing = frappe.db.get_value("Item Price",
        {"item_code": ITEM_CODE, "price_list": PRICE_LIST, "uom": uom},
        ["name", "price_list_rate"], as_dict=True)
    if existing:
        if float(existing.price_list_rate or 0) != precio:
            frappe.db.set_value("Item Price", existing.name, "price_list_rate", precio)
            return "updated"
        return "ok"
    frappe.get_doc({"doctype": "Item Price", "item_code": ITEM_CODE,
                    "price_list": PRICE_LIST, "price_list_rate": precio,
                    "currency": "PYG", "uom": uom}).insert(ignore_permissions=True)
    return "created"


def run(company: str):
    """
    Crea el item Skol Lata 269ml con sus 2 presentaciones.

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_skol_lata.run \
            --kwargs '{"company":"Chamigo E.A.S"}'
    """
    frappe.set_user("Administrator")
    sep = "=" * 52
    print(f"\n{sep}")
    print("  Skol Lata 269ml — configuracion")
    print(f"{sep}\n")

    for uom, _, _, _ in PRESENTATIONS:
        _ensure_uom(uom)
    frappe.db.commit()

    wh  = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
    inc = frappe.db.get_value("Account",
          {"company": company, "account_type": "Income Account", "is_group": 0}, "name")

    if frappe.db.exists("Item", ITEM_CODE):
        log(f"Item ya existe: {ITEM_CODE}", "SKIP")
        doc = frappe.get_doc("Item", ITEM_CODE)
    else:
        doc = frappe.get_doc({
            "doctype": "Item", "item_code": ITEM_CODE, "item_name": ITEM_NAME,
            "item_group": ITEM_GROUP, "stock_uom": STOCK_UOM,
            "purchase_uom": "Pack x15", "sales_uom": STOCK_UOM,
            "is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 1,
            "item_defaults": [{"company": company, "default_warehouse": wh, "income_account": inc}],
        })
        doc.insert(ignore_permissions=True)
        log(f"Item creado: {ITEM_CODE}")

    changed = False
    existing_uoms     = {r.uom: r     for r in doc.uoms}
    existing_barcodes = {r.barcode: r for r in doc.barcodes}

    for uom, factor, barcode, _ in PRESENTATIONS:
        if uom not in existing_uoms:
            doc.append("uoms", {"uom": uom, "conversion_factor": factor})
            log(f"Conversion: 1 {uom} = {factor} {STOCK_UOM}")
            changed = True
        elif existing_uoms[uom].conversion_factor != factor:
            existing_uoms[uom].conversion_factor = factor
            log(f"Conversion actualizada: 1 {uom} = {factor} {STOCK_UOM}")
            changed = True
        else:
            log(f"Conversion OK: {uom}", "SKIP")

        if barcode not in existing_barcodes:
            doc.append("barcodes", {"barcode": barcode, "barcode_type": "EAN", "uom": uom})
            log(f"Barcode: {barcode} -> {uom}")
            changed = True
        else:
            log(f"Barcode OK: {barcode}", "SKIP")

    if changed:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        log("Item guardado")

    for uom, _, _, precio in PRESENTATIONS:
        status = _upsert_price(uom, precio)
        if status == "created":
            log(f"Precio creado [{uom}]: G. {precio:,.0f}")
        elif status == "updated":
            log(f"Precio actualizado [{uom}]: G. {precio:,.0f}")
        else:
            log(f"Precio OK [{uom}]: G. {precio:,.0f}", "SKIP")

    frappe.db.commit()

    print(f"\n{sep}")
    print("  Configuracion completa")
    print("")
    print("  Escanea 7891149103102 -> 1 UNI      -> G.  4.000 -> descuenta  1 UNI")
    print("  Escanea 7840050009157 -> 1 Pack x15  -> G. 57.000 -> descuenta 15 UNI")
    print(f"{sep}\n")


def validate_and_update(company: str):
    """
    Verifica el estado actual del item y aplica las correcciones necesarias.

    Chequea: existencia, UOM conversions, barcodes, precios y stock.

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_skol_lata.validate_and_update \
            --kwargs '{"company":"Chamigo E.A.S"}'
    """
    frappe.set_user("Administrator")
    sep = "=" * 52
    sep2 = "-" * 52
    print(f"\n{sep}")
    print(f"  Validacion — {ITEM_NAME} ({ITEM_CODE})")
    print(f"{sep}\n")

    # Si no existe, crear desde cero
    if not frappe.db.exists("Item", ITEM_CODE):
        log("Item no existe — ejecutando creacion completa...", "WARN")
        run(company)
        return

    doc = frappe.get_doc("Item", ITEM_CODE)
    log(f"Item encontrado: {doc.item_name}")
    log(f"  stock_uom   : {doc.stock_uom}")
    log(f"  purchase_uom: {doc.purchase_uom}")
    log(f"  is_stock    : {doc.is_stock_item}")

    issues = []
    fixes  = []
    changed = False

    # ── Conversiones UOM ─────────────────────────────────────────────────
    print(f"\n  Conversiones UOM:")
    existing_uoms = {r.uom: r for r in doc.uoms}

    for uom, expected_factor, _, _ in PRESENTATIONS:
        _ensure_uom(uom)
        if uom not in existing_uoms:
            doc.append("uoms", {"uom": uom, "conversion_factor": expected_factor})
            issues.append(f"Faltaba conversion: {uom}")
            fixes.append(f"Conversion agregada: 1 {uom} = {expected_factor} {STOCK_UOM}")
            log(f"  FALTA   {uom} (factor {expected_factor}) — agregado", "WARN")
            changed = True
        else:
            actual = existing_uoms[uom].conversion_factor
            if actual != expected_factor:
                existing_uoms[uom].conversion_factor = expected_factor
                issues.append(f"Factor incorrecto {uom}: tenia {actual}")
                fixes.append(f"Factor corregido {uom}: {actual} -> {expected_factor}")
                log(f"  INCORRECTO {uom}: factor {actual} -> {expected_factor}", "WARN")
                changed = True
            else:
                log(f"  OK  1 {uom} = {actual} {STOCK_UOM}")

    # ── Barcodes ─────────────────────────────────────────────────────────
    print(f"\n  Barcodes:")
    existing_barcodes = {r.barcode: r for r in doc.barcodes}

    for uom, _, barcode, _ in PRESENTATIONS:
        if barcode not in existing_barcodes:
            doc.append("barcodes", {"barcode": barcode, "barcode_type": "EAN", "uom": uom})
            issues.append(f"Faltaba barcode: {barcode}")
            fixes.append(f"Barcode agregado: {barcode} -> {uom}")
            log(f"  FALTA   {barcode} ({uom}) — agregado", "WARN")
            changed = True
        else:
            bc_row = existing_barcodes[barcode]
            bc_uom = getattr(bc_row, "uom", None) or ""
            if bc_uom and bc_uom != uom:
                bc_row.uom = uom
                issues.append(f"Barcode {barcode} tenia UOM '{bc_uom}'")
                fixes.append(f"UOM del barcode {barcode}: {bc_uom} -> {uom}")
                log(f"  INCORRECTO {barcode}: UOM {bc_uom} -> {uom}", "WARN")
                changed = True
            else:
                log(f"  OK  {barcode} -> {uom}")

    if changed:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        log("Item guardado con correcciones")

    # ── Precios ───────────────────────────────────────────────────────────
    print(f"\n  Precios en {PRICE_LIST}:")

    for uom, _, _, expected_price in PRESENTATIONS:
        status = _upsert_price(uom, expected_price)
        if status == "created":
            issues.append(f"Faltaba precio [{uom}]")
            fixes.append(f"Precio creado [{uom}]: G. {expected_price:,.0f}")
            log(f"  FALTA   [{uom}] — creado G. {expected_price:,.0f}", "WARN")
        elif status == "updated":
            issues.append(f"Precio incorrecto [{uom}]")
            fixes.append(f"Precio actualizado [{uom}]: G. {expected_price:,.0f}")
            log(f"  ACTUALIZADO [{uom}]: G. {expected_price:,.0f}", "WARN")
        else:
            log(f"  OK  [{uom}]: G. {expected_price:,.0f}")

    frappe.db.commit()

    # ── Stock ─────────────────────────────────────────────────────────────
    print(f"\n  Stock disponible:")
    bins = frappe.get_all("Bin",
        filters={"item_code": ITEM_CODE},
        fields=["warehouse", "actual_qty", "reserved_qty", "ordered_qty"])

    if not bins:
        log("  Sin stock registrado — hacer Material Receipt para cargar stock inicial", "WARN")
    else:
        total = 0
        for b in bins:
            actual   = float(b.actual_qty   or 0)
            reserved = float(b.reserved_qty or 0)
            ordered  = float(b.ordered_qty  or 0)
            packs    = actual / 15
            log(f"  {b.warehouse}")
            log(f"    Disponible : {actual:.0f} UNI = {packs:.1f} Pack x15")
            log(f"    Reservado  : {reserved:.0f} UNI")
            log(f"    En orden   : {ordered:.0f} UNI")
            total += actual
        if len(bins) > 1:
            log(f"  Total general: {total:.0f} UNI = {total/15:.1f} Pack x15")

    # ── Resumen ───────────────────────────────────────────────────────────
    print(f"\n{sep2}")
    n_issues = len(issues)
    n_fixes  = len(fixes)
    if n_issues == 0:
        log(f"Todo en orden — {n_issues} problema(s) encontrado(s)")
    else:
        log(f"{n_issues} problema(s) encontrado(s) — {n_fixes} correccion(es) aplicada(s)", "WARN")
        for i, fix in enumerate(fixes, 1):
            print(f"    {i}. {fix}")
    print(f"{sep}\n")


def cleanup_duplicates(company: str):
    """
    Elimina precios duplicados y corrige purchase_uom.

    Problema: el script corrio varias veces y creo multiples tabItem Price
    para el mismo item+lista sin UOM definida, causando que el POS muestre
    el item duplicado.

    Solucion:
      1. Busca todos los Item Price del item
      2. Para cada combinacion (price_list, uom) deja solo el mas reciente
      3. Elimina los duplicados anteriores
      4. Corrige purchase_uom = Pack x15 en el item

    Uso:
        bench --site erp.chamigo.com.py execute frappe.setup_skol_lata.cleanup_duplicates \
            --kwargs '{"company":"Chamigo E.A.S"}'
    """
    frappe.set_user("Administrator")
    sep = "=" * 52
    print(f"\n{sep}")
    print("  Limpieza de duplicados — Skol Lata 269ml")
    print(f"{sep}\n")

    # ── 1. Listar todos los precios del item ─────────────────────────────
    all_prices = frappe.db.sql("""
        SELECT name, price_list, uom, price_list_rate, creation
        FROM `tabItem Price`
        WHERE item_code = %s
        ORDER BY price_list, uom, creation DESC
    """, ITEM_CODE, as_dict=True)

    log(f"Precios encontrados: {len(all_prices)}")
    for p in all_prices:
        log(f"  {p.name} | {p.price_list} | UOM: '{p.uom}' | G. {float(p.price_list_rate):,.0f}")

    # ── 2. Agrupar por (price_list, uom) y eliminar duplicados ───────────
    print("\n  Eliminando duplicados...")
    seen = {}
    deleted = 0

    for p in all_prices:
        key = (p.price_list, p.uom or "")
        if key not in seen:
            seen[key] = p.name   # conservar el primero (mas reciente por ORDER BY)
        else:
            # Eliminar duplicado
            frappe.db.sql("DELETE FROM `tabItem Price` WHERE name = %s", p.name)
            log(f"  Eliminado duplicado: {p.name} | UOM: '{p.uom}' | G. {float(p.price_list_rate):,.0f}", "WARN")
            deleted += 1

    if deleted == 0:
        log("  Sin duplicados — OK", "SKIP")
    else:
        frappe.db.commit()
        log(f"  {deleted} registro(s) duplicado(s) eliminado(s)")

    # ── 3. Asegurar que los precios correctos existen con UOM ────────────
    print("\n  Verificando precios finales con UOM correcta...")
    for uom, _, _, precio in PRESENTATIONS:
        existing = frappe.db.get_value("Item Price",
            {"item_code": ITEM_CODE, "price_list": PRICE_LIST, "uom": uom},
            ["name", "price_list_rate"], as_dict=True)
        if not existing:
            frappe.get_doc({
                "doctype": "Item Price", "item_code": ITEM_CODE,
                "price_list": PRICE_LIST, "price_list_rate": precio,
                "currency": "PYG", "uom": uom,
            }).insert(ignore_permissions=True)
            log(f"  Precio creado [{uom}]: G. {precio:,.0f}")
        else:
            log(f"  OK [{uom}]: G. {float(existing.price_list_rate):,.0f}")

    frappe.db.commit()

    # ── 4. Corregir purchase_uom en el item ───────────────────────────────
    print("\n  Corrigiendo purchase_uom...")
    current_puom = frappe.db.get_value("Item", ITEM_CODE, "purchase_uom")
    if current_puom != "Pack x15":
        frappe.db.set_value("Item", ITEM_CODE, "purchase_uom", "Pack x15")
        frappe.db.commit()
        log(f"  purchase_uom: '{current_puom}' -> 'Pack x15'")
    else:
        log(f"  purchase_uom OK: Pack x15", "SKIP")

    # ── 5. Estado final ───────────────────────────────────────────────────
    print("\n  Estado final de precios:")
    final_prices = frappe.db.sql("""
        SELECT price_list, uom, price_list_rate
        FROM `tabItem Price`
        WHERE item_code = %s
        ORDER BY price_list, uom
    """, ITEM_CODE, as_dict=True)

    for p in final_prices:
        log(f"  {p.price_list} | UOM: '{p.uom}' | G. {float(p.price_list_rate):,.0f}")

    print(f"\n{sep}")
    log("Limpieza completada")
    print(f"{sep}\n")
