import frappe



def log(msg):
    print(f"[PY] {msg}")

import frappe


def log(msg):
    print(f"[INIT-COA+PAY] {msg}")


def rebuild_coa(company):
    log("Verificando Chart of Accounts...")

    accounts = frappe.get_all(
        "Account",
        filters={"company": company},
        pluck="name"
    )

    if accounts:
        log("Eliminando Chart of Accounts existente...")

        for acc in accounts:
            try:
                frappe.delete_doc("Account", acc, force=1, ignore_permissions=True)
            except Exception as e:
                log(f"Skip {acc}: {e}")

        frappe.db.commit()

    log("Recreando Chart of Accounts desde plantilla...")

    from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts

    create_charts(company, "Paraguay")

    frappe.db.commit()

    log("COA recreado")



def get_account(company, name):
    return frappe.db.get_value(
        "Account",
        {"company": company, "account_name": name},
        "name"
    )



def ensure_extra_accounts(company, abbr):
    log("Creando cuentas adicionales...")

    cash_parent = get_account(company, f"Cash - {abbr}")
    bank_parent = get_account(company, f"Bank Accounts - {abbr}")

    def create(name, parent, type):
        if get_account(company, name):
            return

        frappe.get_doc({
            "doctype": "Account",
            "account_name": name,
            "parent_account": parent,
            "company": company,
            "account_type": type,
            "is_group": 0,
            "currency": "PYG"
        }).insert(ignore_permissions=True)

        log(f"Cuenta creada: {name}")

    create("Caja General", cash_parent, "Cash")
    create("Banco Principal", bank_parent, "Bank")
    create("Billeteras Digitales", bank_parent, "Bank")



def create_mop(name, mop_type, company, account):
    if frappe.db.exists("Mode of Payment", name):
        return

    doc = frappe.get_doc({
        "doctype": "Mode of Payment",
        "mode_of_payment": name,
        "type": mop_type,
        "accounts": [{
            "company": company,
            "default_account": account
        }]
    })

    doc.insert(ignore_permissions=True)
    log(f"MOP: {name}")



def run(company, reset=False):
    try:
        frappe.set_user("Administrator")

        log(f"Empresa: {company}")

        company_doc = frappe.get_doc("Company", company)
        abbr = company_doc.abbr


        if reset:
            rebuild_coa(company)


        ensure_extra_accounts(company, abbr)


        cash = get_account(company, f"Caja General")
        bank = get_account(company, f"Banco Principal")
        qr = get_account(company, f"Billeteras Digitales")

        create_mop("Efectivo", "Cash", company, cash)
        create_mop("Transferencia Bancaria", "Bank", company, bank)
        create_mop("Tarjeta de Crédito", "Bank", company, bank)
        create_mop("Tarjeta de Débito", "Bank", company, bank)
        create_mop("QR / Billetera Digital", "Bank", company, qr)

        frappe.db.commit()

        log("Sistema contable + pagos ")

    except Exception as e:
        frappe.db.rollback()
        log(f"ERROR: {e}")
        raise

    
if __name__ == "__main__":
    run("Chamigo E.A.S", "80136183-4")