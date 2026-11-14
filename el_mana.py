"""El Mana - aplicacion de escritorio (sin navegador)."""
from pathlib import Path
from datetime import date, datetime, timedelta
from tkinter import messagebox, simpledialog, ttk
import tkinter as tk

from facturas import FacturasTab, pedir_sesion

from database import (
    HOJA_CUENTAS_COLUMNAS,
    HOJA_CUENTAS_TITULO,
    crear_trabajador,
    db,
    eliminar_cuenta,
    generar_nomina_semana,
    guardar_asistencia,
    guardar_cuenta,
    init_db,
    listar_asistencia,
    listar_camiones,
    listar_pagos,
    listar_salidas,
    listar_trabajadores,
    marcar_asistencia_dia,
    marcar_pago,
    nombre_jefe,
    get_iva_porcentaje,
    obtener_cuenta,
    obtener_hoja_semanal,
    set_iva_porcentaje,
    registrar_camion as db_registrar_camion,
    registrar_salida,
    registrar_venta_dia_since,
    resumen_app,
    today_iso,
    toggle_trabajador,
)

ROOT = Path(__file__).parent
LOGO_PATH = ROOT / "assets" / "logo.png"

WIDTHS = {
    "fecha": 88,
    "ingreso": 78,
    "ingreso_esp": 130,
    "gastos": 78,
    "gastos_esp": 130,
    "entradas": 78,
    "entradas_esp": 130,
    "activos": 78,
    "activos_esp": 120,
    "creditos": 78,
    "creditos_esp": 110,
    "iva_ingreso": 78,
    "iva_gastos": 78,
    "ganancias": 88,
}
COLS = [(key, title, WIDTHS.get(key, 100)) for key, title in HOJA_CUENTAS_COLUMNAS]

COLOR_GALERAS = "#FFD966"
COLOR_SINCE = "#548235"
COLOR_SINCE_FG = "#FFFFFF"
COLOR_HEADER = "#D9D9D9"
COLOR_GREEN = "#1a3d1f"


def fmt_money(n):
    try:
        return f"{float(n):,.0f}"
    except (TypeError, ValueError):
        return "0"


def fmt_date_display(iso):
    if not iso:
        return ""
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


def parse_date_input(text):
    text = (text or "").strip()
    if not text:
        return today_iso()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Fecha invalida. Use dd/mm/aaaa")


def week_range(ref=None):
    ref = ref or date.today()
    start = ref - timedelta(days=ref.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def parse_num(text):
    if text is None or str(text).strip() == "":
        return 0.0
    return float(str(text).replace(",", "").replace("$", "").strip())


class CuentaDialog(tk.Toplevel):
    def __init__(self, master, sitio, inicio, fin, on_save, row=None):
        super().__init__(master)
        self.sitio = sitio
        self.inicio = inicio
        self.fin = fin
        self.on_save = on_save
        self.row = row
        titulo = "Editar registro" if row else f"Nuevo registro — {sitio.upper()}"
        self.title(titulo)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        fields = [
            ("fecha", "Fecha (dd/mm/aaaa)", fmt_date_display(row["fecha"]) if row else fmt_date_display(today_iso())),
            ("ingreso", "Ingreso ($)", row["ingreso"] if row else 0),
            ("ingreso_esp", "Especificacion ingreso", row["ingreso_esp"] if row else ""),
            ("gastos", "Gastos ($)", row["gastos"] if row else 0),
            ("gastos_esp", "Especificacion gastos", row["gastos_esp"] if row else ""),
            ("entradas", "Entradas (cajas o $)", row["entradas"] if row else 0),
            ("entradas_esp", "Especificacion entradas", row["entradas_esp"] if row else ""),
            ("activos", "Activos ($)", row["activos"] if row else 0),
            ("activos_esp", "Especificacion activos", row["activos_esp"] if row else ""),
            ("creditos", "Creditos ($)", row["creditos"] if row else 0),
            ("creditos_esp", "Especificacion creditos", row["creditos_esp"] if row else ""),
        ]
        self.aplica_iva = tk.BooleanVar(value=bool(row["aplica_iva"]) if row else True)
        self.entries = {}
        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0)
        for i, (key, label, val) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=2)
            e = ttk.Entry(frm, width=36)
            e.grid(row=i, column=1, pady=2, padx=(8, 0))
            e.insert(0, str(val) if val is not None else "")
            self.entries[key] = e

        ttk.Checkbutton(
            frm,
            text=f"Aplica IVA ({get_iva_porcentaje():g}%) sobre ingreso y gastos",
            variable=self.aplica_iva,
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))
        btns = ttk.Frame(frm)
        btns.grid(row=len(fields) + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text="Guardar", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancelar", command=self.destroy).pack(side="left")

    def save(self):
        try:
            data = {
                "sitio": self.sitio,
                "fecha": parse_date_input(self.entries["fecha"].get()),
                "ingreso": parse_num(self.entries["ingreso"].get()),
                "ingreso_esp": self.entries["ingreso_esp"].get().strip(),
                "gastos": parse_num(self.entries["gastos"].get()),
                "gastos_esp": self.entries["gastos_esp"].get().strip(),
                "entradas": parse_num(self.entries["entradas"].get()),
                "entradas_esp": self.entries["entradas_esp"].get().strip(),
                "activos": parse_num(self.entries["activos"].get()),
                "activos_esp": self.entries["activos_esp"].get().strip(),
                "creditos": parse_num(self.entries["creditos"].get()),
                "creditos_esp": self.entries["creditos_esp"].get().strip(),
                "aplica_iva": self.aplica_iva.get(),
            }
            if data["fecha"] < self.inicio or data["fecha"] > self.fin:
                if not messagebox.askyesno(
                    "Fuera de la semana",
                    "La fecha esta fuera del rango seleccionado. ¿Guardar igual?",
                ):
                    return
            if self.row:
                data["id"] = self.row["id"]
            with db() as conn:
                guardar_cuenta(conn, data)
            self.on_save()
            self.destroy()
        except ValueError as ex:
            messagebox.showerror("Error", str(ex), parent=self)


class LedgerSection(ttk.Frame):
    def __init__(self, master, sitio, label, bg, fg="#000000", **kwargs):
        super().__init__(master, **kwargs)
        self.sitio = sitio
        bar = tk.Frame(self, bg=bg, height=28)
        bar.pack(fill="x")
        tk.Label(
            bar,
            text=label,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            padx=8,
        ).pack(fill="x")

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        keys = [c[0] for c in COLS]
        self.tree = ttk.Treeview(tree_frame, columns=keys, show="headings", height=6)
        for key, title, width in COLS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=50, anchor="center")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        totals = ttk.Frame(self, padding=(4, 6))
        totals.pack(fill="x")
        self.lbl_gasto = ttk.Label(totals, text="GASTO TOTAL: 0", font=("Segoe UI", 10, "bold"))
        self.lbl_gasto.pack(side="left", padx=(40, 40))
        self.lbl_total = ttk.Label(totals, text="TOTAL DE CUENTAS: 0", font=("Segoe UI", 10, "bold"))
        self.lbl_total.pack(side="right", padx=8)

    def load(self, rows, totals):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in rows:
            self.tree.insert(
                "",
                "end",
                iid=str(r["id"]),
                values=(
                    fmt_date_display(r["fecha"]),
                    fmt_money(r["ingreso"]),
                    r["ingreso_esp"] or "",
                    fmt_money(r["gastos"]),
                    r["gastos_esp"] or "",
                    fmt_money(r["entradas"]),
                    r["entradas_esp"] or "",
                    fmt_money(r["activos"]),
                    r["activos_esp"] or "",
                    fmt_money(r["creditos"]),
                    r["creditos_esp"] or "",
                    fmt_money(r["iva_ingreso"]),
                    fmt_money(r["iva_gastos"]),
                    fmt_money(r["ganancias"]),
                ),
            )
        self.lbl_gasto.config(
            text=(
                f"GASTO TOTAL: {fmt_money(totals['gasto_total'])}   "
                f"IVA cobrado: {fmt_money(totals['iva_ingreso'])}   "
                f"IVA pagado: {fmt_money(totals['iva_gastos'])}"
            )
        )
        self.lbl_total.config(
            text=f"TOTAL DE CUENTAS: {fmt_money(totals['total_cuentas'])}   IVA a pagar: {fmt_money(totals['iva_a_pagar'])}"
        )

    def selected_row_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])


class ElManaApp(tk.Tk):
    def __init__(self, usuario=None):
        super().__init__()
        self.usuario = usuario or {"usuario": "admin", "nombre": "Propietario", "rol": "administrador"}
        self.title("Microempresa El Maná")
        self.geometry("1360x820")
        self.minsize(1100, 680)
        self.configure(bg="#f4f6ef")
        init_db()
        inicio, fin = week_range()
        self.var_inicio = tk.StringVar(value=fmt_date_display(inicio))
        self.var_fin = tk.StringVar(value=fmt_date_display(fin))
        self.logo_img = None
        self.section_galeras = None
        self.section_since = None
        self._build_ui()
        self.refresh_all()

    def _load_logo(self, parent, size=96):
        if not LOGO_PATH.exists():
            return None
        try:
            img = tk.PhotoImage(file=str(LOGO_PATH))
            w, h = img.width(), img.height()
            factor = max(1, max(w, h) // size)
            if factor > 1:
                img = img.subsample(factor, factor)
            self.logo_img = img
            lbl = tk.Label(parent, image=img, bg=COLOR_GREEN, bd=0)
            return lbl
        except tk.TclError:
            return None

    def _build_ui(self):
        header = tk.Frame(self, bg=COLOR_GREEN)
        header.pack(fill="x")
        logo = self._load_logo(header, size=92)
        if logo:
            logo.pack(side="left", padx=12, pady=8)
        titles = tk.Frame(header, bg=COLOR_GREEN)
        titles.pack(side="left", fill="x", expand=True, pady=10)
        tk.Label(
            titles,
            text="MICROEMPRESA EL MANÁ",
            bg=COLOR_GREEN,
            fg="#FFD966",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            titles,
            text="Gestión documental y contable de facturas  ·  Galeras, Sucre",
            bg=COLOR_GREEN,
            fg="#e8f5e9",
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x")
        self.lbl_jefe = tk.Label(
            titles,
            text="",
            bg=COLOR_GREEN,
            fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.lbl_jefe.pack(fill="x", pady=(6, 0))
        tk.Label(
            titles,
            text="Galeras: bananera  ·  Sincé: distribución",
            bg=COLOR_GREEN,
            fg="#cde8c9",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x")

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="Semana del").pack(side="left")
        ttk.Entry(bar, textvariable=self.var_inicio, width=12).pack(side="left", padx=4)
        ttk.Label(bar, text="al").pack(side="left")
        ttk.Entry(bar, textvariable=self.var_fin, width=12).pack(side="left", padx=4)
        ttk.Button(bar, text="Actualizar", command=self.refresh_all).pack(side="left", padx=8)
        ttk.Button(bar, text="Semana actual", command=self.set_week_today).pack(side="left")
        self.lbl_consolidado = ttk.Label(bar, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_consolidado.pack(side="right", padx=8)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.facturas_tab = FacturasTab(self.nb, self.usuario, on_change=self.refresh_all)
        self.nb.add(self.facturas_tab, text="Facturas")
        self._build_panel_tab()
        self._build_datos_tab()
        self._build_personal_tab()
        self._build_asistencia_tab()
        self._build_pagos_tab()
        self._build_camiones_tab()
        self._build_salidas_tab()

    def _get_range(self):
        inicio = parse_date_input(self.var_inicio.get())
        fin = parse_date_input(self.var_fin.get())
        if inicio > fin:
            raise ValueError("La fecha inicial debe ser menor o igual a la final.")
        return inicio, fin

    def set_week_today(self):
        inicio, fin = week_range()
        self.var_inicio.set(fmt_date_display(inicio))
        self.var_fin.set(fmt_date_display(fin))
        self.refresh_all()

    def refresh_all(self):
        self.refresh_cuentas()
        self.refresh_panel()
        self.refresh_trabajadores()
        self.refresh_asistencia()
        self.refresh_pagos()
        self.refresh_camiones()
        self.refresh_salidas()
        self.lbl_jefe.config(
            text=f"Sesión: {self.usuario['nombre']} ({self.usuario['rol']})  ·  Jefe: {nombre_jefe()}"
        )

    def _build_panel_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="Panel")
        self.panel_cards = ttk.Frame(tab)
        self.panel_cards.pack(fill="x")
        self.panel_labels = {}
        for key, title in [
            ("inventario", "Inventario (cajas)"),
            ("hoja_valor_neto", "Valor neto (hoja)"),
            ("hoja_ingresos", "Ingresos hoja"),
            ("hoja_gastos", "Gastos hoja"),
            ("iva_cobrado", "IVA cobrado"),
            ("iva_pagado", "IVA pagado"),
            ("iva_a_pagar", "IVA a pagar"),
            ("jefe", "Jefe"),
        ]:
            card = ttk.LabelFrame(self.panel_cards, text=title, padding=8)
            card.pack(side="left", fill="x", expand=True, padx=4)
            lbl = ttk.Label(card, text="—", font=("Segoe UI", 14, "bold"))
            lbl.pack()
            self.panel_labels[key] = lbl
        iva_bar = ttk.Frame(tab)
        iva_bar.pack(fill="x", pady=12)
        ttk.Label(iva_bar, text="Porcentaje de IVA:").pack(side="left")
        self.var_iva = tk.StringVar(value=str(get_iva_porcentaje()).replace(".0", ""))
        ttk.Entry(iva_bar, textvariable=self.var_iva, width=6).pack(side="left", padx=4)
        ttk.Label(iva_bar, text="%").pack(side="left")
        ttk.Button(iva_bar, text="Guardar IVA", command=self.guardar_iva).pack(side="left", padx=8)
        ttk.Label(
            iva_bar,
            text="En Datos, marque “Aplica IVA” en cada fila. Nómina no lleva IVA. Ventas sí, por defecto.",
        ).pack(side="left", padx=8)
        ttk.Label(
            tab,
            text="La pestaña Datos es la hoja principal. Ahí se ingresan ingresos, gastos, entradas, activos, créditos e IVA de Galeras y Sincé.",
            wraplength=1100,
        ).pack(anchor="w", pady=4)

    def refresh_panel(self):
        try:
            inicio, fin = self._get_range()
        except ValueError:
            return
        r = resumen_app(inicio, fin)
        self.panel_labels["inventario"].config(text=fmt_money(r.get("inventario", 0)))
        self.panel_labels["hoja_valor_neto"].config(text=fmt_money(r.get("hoja_valor_neto", 0)))
        self.panel_labels["hoja_ingresos"].config(text=fmt_money(r.get("hoja_ingresos", 0)))
        self.panel_labels["hoja_gastos"].config(text=fmt_money(r.get("hoja_gastos", 0)))
        self.panel_labels["iva_cobrado"].config(text=fmt_money(r.get("iva_cobrado", 0)))
        self.panel_labels["iva_pagado"].config(text=fmt_money(r.get("iva_pagado", 0)))
        self.panel_labels["iva_a_pagar"].config(text=fmt_money(r.get("iva_a_pagar", 0)))
        self.panel_labels["jefe"].config(text=nombre_jefe())
        self.var_iva.set(str(r.get("iva_porcentaje", get_iva_porcentaje())).replace(".0", ""))

    def guardar_iva(self):
        try:
            set_iva_porcentaje(parse_num(self.var_iva.get()))
            messagebox.showinfo("IVA", f"IVA guardado: {get_iva_porcentaje():g}%")
            self.refresh_all()
        except ValueError as ex:
            messagebox.showerror("IVA", str(ex))

    def _build_datos_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Datos")
        ttk.Label(
            tab,
            text=HOJA_CUENTAS_TITULO,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            tab,
            text="Hoja principal: ingrese aquí lo de cada día, como en Excel. Galeras = finca. Sincé = distribución.",
        ).pack(anchor="w", pady=(0, 6))

        tools_g = ttk.Frame(tab)
        tools_g.pack(fill="x")
        ttk.Button(tools_g, text="+ Fila Galeras", command=lambda: self.add_row("galeras")).pack(side="left", padx=2)
        ttk.Button(tools_g, text="Editar Galeras", command=lambda: self.edit_row("galeras")).pack(side="left", padx=2)
        ttk.Button(tools_g, text="Eliminar Galeras", command=lambda: self.delete_row("galeras")).pack(side="left", padx=2)

        self.section_galeras = LedgerSection(tab, "galeras", "GALERAS", COLOR_GALERAS)
        self.section_galeras.pack(fill="both", expand=True, pady=4)

        tools_s = ttk.Frame(tab)
        tools_s.pack(fill="x")
        ttk.Button(tools_s, text="+ Fila Sincé", command=lambda: self.add_row("since")).pack(side="left", padx=2)
        ttk.Button(tools_s, text="Editar Sincé", command=lambda: self.edit_row("since")).pack(side="left", padx=2)
        ttk.Button(tools_s, text="Eliminar Sincé", command=lambda: self.delete_row("since")).pack(side="left", padx=2)
        ttk.Button(tools_s, text="Venta del día (Sincé)", command=self.venta_dia_since).pack(side="left", padx=8)

        self.section_since = LedgerSection(tab, "since", "SINCÉ", COLOR_SINCE, fg=COLOR_SINCE_FG)
        self.section_since.pack(fill="both", expand=True, pady=(0, 4))

    def refresh_cuentas(self):
        try:
            inicio, fin = self._get_range()
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))
            return
        hoja = obtener_hoja_semanal(inicio, fin)
        c = hoja["consolidado"]
        self.lbl_consolidado.config(
            text=(
                f"GASTO TOTAL: {fmt_money(c['gasto_total'])}   "
                f"TOTAL DE CUENTAS: {fmt_money(c['total_cuentas'])}   "
                f"IVA A PAGAR: {fmt_money(c['iva_a_pagar'])}"
            )
        )
        self.section_galeras.load(hoja["galeras"]["filas"], hoja["galeras"]["totales"])
        self.section_since.load(hoja["since"]["filas"], hoja["since"]["totales"])

    def add_row(self, sitio):
        try:
            inicio, fin = self._get_range()
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))
            return
        CuentaDialog(self, sitio, inicio, fin, self.refresh_all)

    def edit_row(self, sitio):
        section = self.section_galeras if sitio == "galeras" else self.section_since
        rid = section.selected_row_id()
        if not rid:
            messagebox.showinfo("Editar", "Seleccione una fila en Datos.")
            return
        with db() as conn:
            row = obtener_cuenta(conn, rid)
        try:
            inicio, fin = self._get_range()
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))
            return
        CuentaDialog(self, sitio, inicio, fin, self.refresh_all, row=row)

    def delete_row(self, sitio):
        section = self.section_galeras if sitio == "galeras" else self.section_since
        rid = section.selected_row_id()
        if not rid:
            messagebox.showinfo("Eliminar", "Seleccione una fila en Datos.")
            return
        if messagebox.askyesno("Confirmar", "¿Eliminar este registro?"):
            with db() as conn:
                eliminar_cuenta(conn, rid)
            self.refresh_all()

    def venta_dia_since(self):
        try:
            _inicio, fin = self._get_range()
            monto = simpledialog.askfloat("Venta del día", "Monto de venta en Sincé ($):", parent=self, minvalue=0)
            if monto is None:
                return
            registrar_venta_dia_since(fin, monto)
            self.refresh_all()
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))

    def _build_personal_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Trabajadores")
        form = ttk.LabelFrame(tab, text="Registrar persona", padding=8)
        form.pack(fill="x")
        grid = ttk.Frame(form)
        grid.pack(fill="x")
        self.trab_nombre = ttk.Entry(grid, width=24)
        self.trab_cedula = ttk.Entry(grid, width=14)
        self.trab_tel = ttk.Entry(grid, width=14)
        self.trab_tarifa = ttk.Entry(grid, width=12)
        self.trab_cargo = ttk.Combobox(
            grid,
            values=["Jefe", "Supervisor", "Cosechador", "Empacador", "Conductor", "Administrativo"],
            state="readonly",
            width=16,
        )
        self.trab_cargo.set("Cosechador")
        campos = [
            ("Nombre", self.trab_nombre),
            ("Cédula", self.trab_cedula),
            ("Cargo", self.trab_cargo),
            ("Tarifa diaria $", self.trab_tarifa),
            ("Teléfono", self.trab_tel),
        ]
        for i, (lbl, w) in enumerate(campos):
            ttk.Label(grid, text=lbl).grid(row=0, column=i, sticky="w", padx=4)
            w.grid(row=1, column=i, padx=4, pady=2)
        ttk.Button(form, text="Agregar", command=self.add_trabajador).pack(anchor="w", pady=6)

        self.tree_trab = ttk.Treeview(
            tab,
            columns=("nombre", "cedula", "cargo", "tarifa", "telefono", "estado"),
            show="headings",
            height=14,
        )
        for c, t, w in [
            ("nombre", "Nombre", 180),
            ("cedula", "Cédula", 110),
            ("cargo", "Cargo", 120),
            ("tarifa", "Pago / día", 100),
            ("telefono", "Teléfono", 110),
            ("estado", "Estado", 80),
        ]:
            self.tree_trab.heading(c, text=t)
            self.tree_trab.column(c, width=w)
        self.tree_trab.pack(fill="both", expand=True, pady=8)
        ttk.Button(tab, text="Activar / desactivar seleccionado", command=self.toggle_sel_trabajador).pack(anchor="w")

    def add_trabajador(self):
        nombre = self.trab_nombre.get().strip()
        if not nombre:
            messagebox.showerror("Error", "Escriba el nombre.")
            return
        try:
            tarifa = parse_num(self.trab_tarifa.get())
        except ValueError:
            messagebox.showerror("Error", "Tarifa inválida.")
            return
        crear_trabajador(
            nombre,
            tarifa,
            cargo=self.trab_cargo.get() or "Cosechador",
            cedula=self.trab_cedula.get().strip(),
            telefono=self.trab_tel.get().strip(),
        )
        self.trab_nombre.delete(0, "end")
        self.trab_cedula.delete(0, "end")
        self.trab_tel.delete(0, "end")
        self.trab_tarifa.delete(0, "end")
        self.refresh_all()

    def toggle_sel_trabajador(self):
        sel = self.tree_trab.selection()
        if not sel:
            messagebox.showinfo("Trabajadores", "Seleccione una persona.")
            return
        toggle_trabajador(int(sel[0]))
        self.refresh_all()

    def refresh_trabajadores(self):
        if not hasattr(self, "tree_trab"):
            return
        for i in self.tree_trab.get_children():
            self.tree_trab.delete(i)
        for r in listar_trabajadores():
            self.tree_trab.insert(
                "",
                "end",
                iid=str(r["id"]),
                values=(
                    r["nombre"],
                    r["cedula"] or "",
                    r["cargo"] or "",
                    fmt_money(r["tarifa_diaria"]),
                    r["telefono"] or "",
                    "Activo" if r["activo"] else "Inactivo",
                ),
            )

    def _build_asistencia_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Asistencia")
        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Label(row, text="Fecha").pack(side="left")
        self.asist_fecha = ttk.Entry(row, width=12)
        self.asist_fecha.insert(0, fmt_date_display(today_iso()))
        self.asist_fecha.pack(side="left", padx=6)
        ttk.Button(row, text="Cargar", command=self.refresh_asistencia).pack(side="left")
        ttk.Button(row, text="Todos presentes", command=self.marcar_presentes).pack(side="left", padx=8)
        self.lbl_asist = ttk.Label(row, text="")
        self.lbl_asist.pack(side="left", padx=12)

        self.tree_asist = ttk.Treeview(
            tab,
            columns=("nombre", "cargo", "presente", "motivo"),
            show="headings",
            height=16,
        )
        for c, t, w in [
            ("nombre", "Nombre", 180),
            ("cargo", "Cargo", 120),
            ("presente", "Presente", 90),
            ("motivo", "Motivo si falta", 260),
        ]:
            self.tree_asist.heading(c, text=t)
            self.tree_asist.column(c, width=w)
        self.tree_asist.pack(fill="both", expand=True, pady=8)
        self.tree_asist.bind("<Double-1>", self._toggle_asist_row)
        ttk.Label(tab, text="Doble clic en una fila para marcar presente / ausente. Luego Guardar.").pack(anchor="w")
        ttk.Button(tab, text="Guardar asistencia", command=self.guardar_asist).pack(anchor="w", pady=6)
        self._asist_state = {}

    def _toggle_asist_row(self, _event=None):
        sel = self.tree_asist.selection()
        if not sel:
            return
        iid = sel[0]
        vals = list(self.tree_asist.item(iid, "values"))
        presente = vals[2] != "Sí"
        vals[2] = "Sí" if presente else "No"
        if presente:
            vals[3] = ""
        else:
            motivo = simpledialog.askstring("Ausencia", "Motivo de la ausencia:", parent=self)
            vals[3] = motivo or "Sin motivo"
        self.tree_asist.item(iid, values=vals)
        self._asist_state[int(iid)] = {"presente": presente, "motivo": vals[3]}

    def guardar_asist(self):
        try:
            fecha = parse_date_input(self.asist_fecha.get())
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))
            return
        items = []
        for iid in self.tree_asist.get_children():
            vals = self.tree_asist.item(iid, "values")
            items.append(
                {
                    "trabajador_id": int(iid),
                    "presente": vals[2] == "Sí",
                    "motivo": vals[3],
                }
            )
        if not items:
            messagebox.showinfo("Asistencia", "No hay trabajadores activos.")
            return
        guardar_asistencia(fecha, items)
        messagebox.showinfo("Asistencia", "Asistencia guardada.")
        self.refresh_asistencia()

    def marcar_presentes(self):
        try:
            fecha = parse_date_input(self.asist_fecha.get())
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))
            return
        marcar_asistencia_dia(fecha, presente=True)
        self.refresh_asistencia()

    def refresh_asistencia(self):
        if not hasattr(self, "tree_asist"):
            return
        try:
            fecha = parse_date_input(self.asist_fecha.get())
        except ValueError:
            return
        workers, registros, resumen = listar_asistencia(fecha)
        for i in self.tree_asist.get_children():
            self.tree_asist.delete(i)
        self._asist_state = {}
        for w in workers:
            reg = registros.get(w["id"])
            presente = True if not reg else bool(reg["presente"])
            motivo = "" if presente else (reg["motivo_ausencia"] if reg else "")
            self.tree_asist.insert(
                "",
                "end",
                iid=str(w["id"]),
                values=(w["nombre"], w["cargo"], "Sí" if presente else "No", motivo or ""),
            )
        self.lbl_asist.config(
            text=f"Presentes: {resumen['presentes'] or 0}   Ausentes: {resumen['ausentes'] or 0}"
        )

    def _build_pagos_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Pagos")
        ttk.Label(
            tab,
            text="La nómina usa asistencia × tarifa diaria. Al generarla también entra como gasto en Datos (Galeras).",
        ).pack(anchor="w")
        ttk.Button(tab, text="Generar nómina de la semana", command=self.generar_nomina).pack(anchor="w", pady=8)
        self.lbl_nomina = ttk.Label(tab, text="")
        self.lbl_nomina.pack(anchor="w")
        self.tree_pagos = ttk.Treeview(
            tab,
            columns=("nombre", "cargo", "periodo", "dias", "monto", "estado"),
            show="headings",
            height=14,
        )
        for c, t, w in [
            ("nombre", "Trabajador / jefe", 180),
            ("cargo", "Cargo", 110),
            ("periodo", "Periodo", 180),
            ("dias", "Días", 60),
            ("monto", "Pago", 100),
            ("estado", "Estado", 120),
        ]:
            self.tree_pagos.heading(c, text=t)
            self.tree_pagos.column(c, width=w)
        self.tree_pagos.pack(fill="both", expand=True, pady=8)
        ttk.Button(tab, text="Marcar pagado", command=self.marcar_pagado_sel).pack(anchor="w")

    def generar_nomina(self):
        try:
            inicio, fin = self._get_range()
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))
            return
        result = generar_nomina_semana(inicio, fin, sync_hoja=True)
        self.lbl_nomina.config(
            text=f"Nómina: {result['generados']} persona(s) · Total {fmt_money(result['total'])}"
        )
        self.refresh_all()
        messagebox.showinfo("Nómina", f"Generada para {result['generados']} persona(s).")

    def marcar_pagado_sel(self):
        sel = self.tree_pagos.selection()
        if not sel:
            messagebox.showinfo("Pagos", "Seleccione un pago.")
            return
        marcar_pago(int(sel[0]))
        self.refresh_pagos()

    def refresh_pagos(self):
        if not hasattr(self, "tree_pagos"):
            return
        for i in self.tree_pagos.get_children():
            self.tree_pagos.delete(i)
        for p in listar_pagos():
            estado = f"Pagado {fmt_date_display(p['fecha_pago'])}" if p["pagado"] else "Pendiente"
            self.tree_pagos.insert(
                "",
                "end",
                iid=str(p["id"]),
                values=(
                    p["trabajador_nombre"],
                    p["cargo"] or "",
                    f"{fmt_date_display(p['periodo_inicio'])} → {fmt_date_display(p['periodo_fin'])}",
                    p["dias_trabajados"],
                    fmt_money(p["monto"]),
                    estado,
                ),
            )

    def _build_camiones_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Camiones")
        ttk.Label(tab, text="Llegada de banano a Galeras. Si marca la casilla, también se escribe en la pestaña Datos.").pack(anchor="w")
        form = ttk.LabelFrame(tab, text="Nuevo camión", padding=8)
        form.pack(fill="x", pady=8)
        grid = ttk.Frame(form)
        grid.pack(fill="x")
        self.cam_fecha = ttk.Entry(grid, width=12)
        self.cam_fecha.insert(0, fmt_date_display(today_iso()))
        self.cam_placa = ttk.Entry(grid, width=12)
        self.cam_cajas = ttk.Entry(grid, width=10)
        self.cam_precio = ttk.Entry(grid, width=10)
        self.cam_cond = ttk.Entry(grid, width=20)
        for i, (lbl, w) in enumerate(
            [
                ("Fecha", self.cam_fecha),
                ("Placa", self.cam_placa),
                ("Conductor", self.cam_cond),
                ("Cajas", self.cam_cajas),
                ("Precio/caja", self.cam_precio),
            ]
        ):
            ttk.Label(grid, text=lbl).grid(row=0, column=i * 2, sticky="w", padx=2)
            w.grid(row=0, column=i * 2 + 1, padx=4)
        self.cam_sync = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Agregar a la hoja de Datos (Galeras)", variable=self.cam_sync).pack(anchor="w", pady=4)
        ttk.Button(form, text="Registrar camión", command=self.registrar_camion).pack(anchor="w")
        self.tree_cam = ttk.Treeview(
            tab, columns=("fecha", "placa", "cond", "cajas", "precio"), show="headings", height=12
        )
        for c, t, w in [
            ("fecha", "Fecha", 90),
            ("placa", "Placa", 80),
            ("cond", "Conductor", 140),
            ("cajas", "Cajas", 70),
            ("precio", "Precio/caja", 90),
        ]:
            self.tree_cam.heading(c, text=t)
            self.tree_cam.column(c, width=w)
        self.tree_cam.pack(fill="both", expand=True, pady=8)

    def registrar_camion(self):
        try:
            db_registrar_camion(
                parse_date_input(self.cam_fecha.get()),
                self.cam_placa.get().strip(),
                self.cam_cond.get().strip(),
                parse_num(self.cam_cajas.get()),
                parse_num(self.cam_precio.get()),
                sync_hoja=self.cam_sync.get(),
            )
            self.cam_cajas.delete(0, "end")
            self.refresh_all()
            messagebox.showinfo("Camión", "Camión registrado.")
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))

    def refresh_camiones(self):
        if not hasattr(self, "tree_cam"):
            return
        for i in self.tree_cam.get_children():
            self.tree_cam.delete(i)
        for r in listar_camiones():
            self.tree_cam.insert(
                "",
                "end",
                values=(
                    fmt_date_display(r["fecha"]),
                    r["placa"] or "",
                    r["conductor"] or "",
                    fmt_money(r["cantidad_cajas"]),
                    fmt_money(r["precio_compra_caja"]),
                ),
            )

    def _build_salidas_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Salidas")
        ttk.Label(tab, text="Despacho / venta. Por defecto se anota en Sincé (distribución) y en la hoja Datos.").pack(anchor="w")
        form = ttk.LabelFrame(tab, text="Nueva salida", padding=8)
        form.pack(fill="x", pady=8)
        grid = ttk.Frame(form)
        grid.pack(fill="x")
        self.sal_fecha = ttk.Entry(grid, width=12)
        self.sal_fecha.insert(0, fmt_date_display(today_iso()))
        self.sal_cajas = ttk.Entry(grid, width=10)
        self.sal_precio = ttk.Entry(grid, width=10)
        self.sal_dest = ttk.Entry(grid, width=22)
        self.sal_sitio = ttk.Combobox(grid, values=["since", "galeras"], state="readonly", width=10)
        self.sal_sitio.set("since")
        for i, (lbl, w) in enumerate(
            [
                ("Fecha", self.sal_fecha),
                ("Cajas", self.sal_cajas),
                ("Precio venta/caja", self.sal_precio),
                ("Destino", self.sal_dest),
                ("Sitio", self.sal_sitio),
            ]
        ):
            ttk.Label(grid, text=lbl).grid(row=0, column=i, sticky="w", padx=4)
            w.grid(row=1, column=i, padx=4)
        ttk.Button(form, text="Registrar salida", command=self.registrar_salida_ui).pack(anchor="w", pady=6)
        self.tree_sal = ttk.Treeview(
            tab, columns=("fecha", "sitio", "destino", "cajas", "precio", "total"), show="headings", height=12
        )
        for c, t, w in [
            ("fecha", "Fecha", 90),
            ("sitio", "Sitio", 80),
            ("destino", "Destino", 180),
            ("cajas", "Cajas", 70),
            ("precio", "Precio", 90),
            ("total", "Total", 100),
        ]:
            self.tree_sal.heading(c, text=t)
            self.tree_sal.column(c, width=w)
        self.tree_sal.pack(fill="both", expand=True, pady=8)

    def registrar_salida_ui(self):
        try:
            registrar_salida(
                parse_date_input(self.sal_fecha.get()),
                parse_num(self.sal_cajas.get()),
                self.sal_dest.get().strip() or "Venta del día",
                parse_num(self.sal_precio.get()),
                sitio=self.sal_sitio.get() or "since",
                sync_hoja=True,
            )
            self.sal_cajas.delete(0, "end")
            self.refresh_all()
            messagebox.showinfo("Salida", "Salida registrada en inventario y en Datos.")
        except ValueError as ex:
            messagebox.showerror("Error", str(ex))

    def refresh_salidas(self):
        if not hasattr(self, "tree_sal"):
            return
        for i in self.tree_sal.get_children():
            self.tree_sal.delete(i)
        for r in listar_salidas():
            total = (r["cantidad_cajas"] or 0) * (r["precio_venta_caja"] or 0)
            self.tree_sal.insert(
                "",
                "end",
                values=(
                    fmt_date_display(r["fecha"]),
                    (r["sitio"] or "").capitalize(),
                    r["destino"] or "",
                    fmt_money(r["cantidad_cajas"]),
                    fmt_money(r["precio_venta_caja"]),
                    fmt_money(total),
                ),
            )


def main():
    try:
        usuario = pedir_sesion()
        if not usuario:
            return
        app = ElManaApp(usuario)
        app.mainloop()
    except Exception as ex:
        messagebox.showerror("El Mana", f"No se pudo iniciar la aplicación:\n{ex}")
        raise


if __name__ == "__main__":
    main()
