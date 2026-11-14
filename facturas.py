"""Facturas, soportes, reporte DIAN, usuarios y copia de seguridad."""
from __future__ import annotations

import csv
import hashlib
import re
import secrets
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk

from database import (
    db,
    fetch_all,
    fetch_one,
    get_iva_porcentaje,
    guardar_cuenta,
    now_iso,
    today_iso,
)

ROOT = Path(__file__).parent
SOPORTES = ROOT / "soportes"
DB_PATH = ROOT / "el_mana.db"
MAX_BYTES = 5 * 1024 * 1024
CATEGORIAS = ("fertilizantes", "fungicidas", "empaques", "venta de banano", "otros")
TIPOS = ("compra", "venta")


def hash_password(password: str, salt: str | None = None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), 120_000).hex()
    return salt, digest


def autenticar(usuario: str, password: str):
    with db() as conn:
        row = fetch_one(
            conn,
            "SELECT * FROM usuarios WHERE usuario = ? AND activo = 1",
            (usuario.strip().lower(),),
        )
    if not row:
        return None
    _salt, digest = hash_password(password, row["salt"])
    if digest != row["password_hash"]:
        return None
    return {"id": row["id"], "usuario": row["usuario"], "nombre": row["nombre"], "rol": row["rol"]}


def es_admin(usuario) -> bool:
    return bool(usuario) and usuario.get("rol") == "administrador"


def _nit_limpio(nit: str) -> str:
    return re.sub(r"[\s.\-]", "", (nit or "").strip())


def validar_factura(data: dict, factura_id=None):
    tipo = (data.get("tipo") or "").strip().lower()
    if tipo not in TIPOS:
        raise ValueError("El tipo debe ser compra o venta.")
    numero = (data.get("numero") or "").strip()
    if not numero:
        raise ValueError("El número de factura es obligatorio.")
    nit = _nit_limpio(data.get("nit") or "")
    if not nit.isdigit():
        raise ValueError("El NIT o la cédula deben ser solo números.")
    razon = (data.get("razon_social") or "").strip()
    if not razon:
        raise ValueError("La razón social es obligatoria.")
    categoria = (data.get("categoria") or "").strip().lower()
    if categoria not in CATEGORIAS:
        raise ValueError("Elija una categoría válida.")
    fecha = _parse_fecha(data.get("fecha"))
    if fecha > date.today():
        raise ValueError("La fecha de emisión no puede ser futura.")
    try:
        valor = float(data.get("valor") or 0)
    except (TypeError, ValueError):
        raise ValueError("El valor antes de IVA debe ser un número.")
    if valor <= 0:
        raise ValueError("El valor antes de IVA debe ser mayor que cero.")
    try:
        pct = float(data.get("iva_porcentaje") if data.get("iva_porcentaje") not in (None, "") else get_iva_porcentaje())
    except (TypeError, ValueError):
        raise ValueError("El porcentaje de IVA no es válido.")
    if pct < 0 or pct > 100:
        raise ValueError("El IVA debe estar entre 0 y 100.")
    with db() as conn:
        dup = fetch_one(
            conn,
            """
            SELECT id FROM facturas
            WHERE tipo = ? AND nit = ? AND numero = ? AND id != ?
            """,
            (tipo, nit, numero, factura_id or 0),
        )
    if dup:
        raise ValueError("Ya existe una factura con el mismo tipo, NIT y número.")
    iva = round(valor * pct / 100.0, 2)
    total = round(valor + iva, 2)
    return {
        "tipo": tipo,
        "numero": numero,
        "fecha_emision": fecha.isoformat(),
        "nit": nit,
        "razon_social": razon,
        "categoria": categoria,
        "valor_antes_iva": valor,
        "iva_porcentaje": pct,
        "iva": iva,
        "total": total,
    }


def _parse_fecha(text) -> date:
    text = (text or "").strip()
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(text)[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError("Fecha inválida. Use dd/mm/aaaa.")


def guardar_factura(data: dict, usuario: dict, factura_id=None):
    if not es_admin(usuario):
        raise ValueError("Solo el administrador puede registrar o editar facturas.")
    limpio = validar_factura(data, factura_id)
    ahora = now_iso()
    quien = usuario["usuario"]
    with db() as conn:
        if factura_id:
            actual = fetch_one(conn, "SELECT * FROM facturas WHERE id = ?", (factura_id,))
            if not actual:
                raise ValueError("La factura no existe.")
            if actual["estado"] != "activa":
                raise ValueError("No se puede editar una factura anulada.")
            conn.execute(
                """
                UPDATE facturas SET
                    tipo=?, numero=?, fecha_emision=?, nit=?, razon_social=?, categoria=?,
                    valor_antes_iva=?, iva_porcentaje=?, iva=?, total=?,
                    editado_por=?, editado_en=?
                WHERE id=?
                """,
                (
                    limpio["tipo"],
                    limpio["numero"],
                    limpio["fecha_emision"],
                    limpio["nit"],
                    limpio["razon_social"],
                    limpio["categoria"],
                    limpio["valor_antes_iva"],
                    limpio["iva_porcentaje"],
                    limpio["iva"],
                    limpio["total"],
                    quien,
                    ahora,
                    factura_id,
                ),
            )
            _evento(conn, factura_id, "editar", quien, "Factura actualizada")
            return factura_id
        cur = conn.execute(
            """
            INSERT INTO facturas (
                tipo, numero, fecha_emision, nit, razon_social, categoria,
                valor_antes_iva, iva_porcentaje, iva, total, creado_por, creado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                limpio["tipo"],
                limpio["numero"],
                limpio["fecha_emision"],
                limpio["nit"],
                limpio["razon_social"],
                limpio["categoria"],
                limpio["valor_antes_iva"],
                limpio["iva_porcentaje"],
                limpio["iva"],
                limpio["total"],
                quien,
                ahora,
            ),
        )
        nuevo = cur.lastrowid
        _evento(conn, nuevo, "crear", quien, "Factura registrada")
        return nuevo


def anular_factura(factura_id: int, usuario: dict, motivo: str):
    if not es_admin(usuario):
        raise ValueError("Solo el administrador puede anular facturas.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escriba el motivo de la anulación.")
    ahora = now_iso()
    with db() as conn:
        actual = fetch_one(conn, "SELECT estado FROM facturas WHERE id = ?", (factura_id,))
        if not actual:
            raise ValueError("La factura no existe.")
        if actual["estado"] == "anulada":
            raise ValueError("La factura ya está anulada.")
        conn.execute(
            """
            UPDATE facturas
            SET estado='anulada', anulado_por=?, anulado_en=?, motivo_anulacion=?
            WHERE id=?
            """,
            (usuario["usuario"], ahora, motivo, factura_id),
        )
        _evento(conn, factura_id, "anular", usuario["usuario"], motivo)


def _evento(conn, factura_id, accion, usuario, detalle):
    conn.execute(
        """
        INSERT INTO factura_eventos (factura_id, accion, usuario, cuando, detalle)
        VALUES (?, ?, ?, ?, ?)
        """,
        (factura_id, accion, usuario, now_iso(), detalle),
    )


def buscar_facturas(filtros: dict):
    sql = ["SELECT f.*, s.ruta AS soporte_ruta, s.tamano AS soporte_tamano, s.hash AS soporte_hash FROM facturas f LEFT JOIN soportes s ON s.factura_id = f.id WHERE 1=1"]
    params = []
    if filtros.get("nit"):
        sql.append("AND f.nit LIKE ?")
        params.append(f"%{_nit_limpio(filtros['nit'])}%")
    if filtros.get("razon_social"):
        sql.append("AND f.razon_social LIKE ?")
        params.append(f"%{filtros['razon_social'].strip()}%")
    if filtros.get("numero"):
        sql.append("AND f.numero LIKE ?")
        params.append(f"%{filtros['numero'].strip()}%")
    if filtros.get("tipo") in TIPOS:
        sql.append("AND f.tipo = ?")
        params.append(filtros["tipo"])
    if filtros.get("categoria") in CATEGORIAS:
        sql.append("AND f.categoria = ?")
        params.append(filtros["categoria"])
    if filtros.get("desde"):
        sql.append("AND f.fecha_emision >= ?")
        params.append(_parse_fecha(filtros["desde"]).isoformat())
    if filtros.get("hasta"):
        sql.append("AND f.fecha_emision <= ?")
        params.append(_parse_fecha(filtros["hasta"]).isoformat())
    sql.append("ORDER BY f.fecha_emision DESC, f.id DESC")
    with db() as conn:
        return fetch_all(conn, " ".join(sql), params)


def totales_facturas(filas):
    activas = [f for f in filas if f["estado"] == "activa"]
    ventas = [f for f in activas if f["tipo"] == "venta"]
    compras = [f for f in activas if f["tipo"] == "compra"]
    iva_ventas = sum(float(f["iva"] or 0) for f in ventas)
    iva_compras = sum(float(f["iva"] or 0) for f in compras)
    return {
        "cantidad": len(activas),
        "anuladas": sum(1 for f in filas if f["estado"] == "anulada"),
        "ventas": sum(float(f["total"] or 0) for f in ventas),
        "compras": sum(float(f["total"] or 0) for f in compras),
        "base_ventas": sum(float(f["valor_antes_iva"] or 0) for f in ventas),
        "base_compras": sum(float(f["valor_antes_iva"] or 0) for f in compras),
        "iva_ventas": iva_ventas,
        "iva_compras": iva_compras,
        "iva_a_pagar": iva_ventas - iva_compras,
    }


def exportar_csv(filas, destino: Path):
    tot = totales_facturas(filas)
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "tipo",
                "numero",
                "fecha_emision",
                "nit",
                "razon_social",
                "categoria",
                "valor_antes_iva",
                "iva",
                "total",
                "estado",
                "creado_por",
                "creado_en",
                "editado_por",
                "editado_en",
                "anulado_por",
                "anulado_en",
                "motivo_anulacion",
                "soporte",
            ]
        )
        for f in filas:
            writer.writerow(
                [
                    f["tipo"],
                    f["numero"],
                    f["fecha_emision"],
                    f["nit"],
                    f["razon_social"],
                    f["categoria"],
                    f["valor_antes_iva"],
                    f["iva"],
                    f["total"],
                    f["estado"],
                    f["creado_por"],
                    f["creado_en"],
                    f["editado_por"] or "",
                    f["editado_en"] or "",
                    f["anulado_por"] or "",
                    f["anulado_en"] or "",
                    f["motivo_anulacion"] or "",
                    f["soporte_ruta"] or "",
                ]
            )
        writer.writerow([])
        writer.writerow(["RESUMEN DIAN"])
        writer.writerow(["facturas_activas", tot["cantidad"]])
        writer.writerow(["anuladas", tot["anuladas"]])
        writer.writerow(["base_ventas", tot["base_ventas"]])
        writer.writerow(["iva_ventas", tot["iva_ventas"]])
        writer.writerow(["total_ventas", tot["ventas"]])
        writer.writerow(["base_compras", tot["base_compras"]])
        writer.writerow(["iva_compras", tot["iva_compras"]])
        writer.writerow(["total_compras", tot["compras"]])
        writer.writerow(["iva_a_pagar", tot["iva_a_pagar"]])


def adjuntar_soporte(factura_id: int, origen: Path, usuario: dict):
    if not es_admin(usuario):
        raise ValueError("Solo el administrador puede adjuntar soportes.")
    origen = Path(origen)
    ext = origen.suffix.lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise ValueError("Solo se aceptan archivos PDF, JPG o PNG.")
    if not origen.is_file():
        raise ValueError("No se encontró el archivo.")
    if origen.stat().st_size > MAX_BYTES:
        raise ValueError("El archivo supera 5 MB.")
    hoy = date.today()
    carpeta = SOPORTES / f"{hoy.year}" / f"{hoy.month:02d}"
    carpeta.mkdir(parents=True, exist_ok=True)
    if ext == ".pdf":
        temporal = carpeta / f"tmp-{secrets.token_hex(4)}.pdf"
        shutil.copy2(origen, temporal)
    else:
        temporal = _comprimir_imagen(origen, carpeta)
        if temporal.stat().st_size > MAX_BYTES:
            temporal.unlink(missing_ok=True)
            raise ValueError("La imagen sigue superando 5 MB después de comprimirla.")
    data = temporal.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    final = carpeta / f"{digest[:16]}{temporal.suffix.lower()}"
    if final.exists():
        temporal.unlink(missing_ok=True)
    else:
        temporal.replace(final)
    ruta_rel = str(final.relative_to(ROOT)).replace("\\", "/")
    tamano = final.stat().st_size
    with db() as conn:
        if not fetch_one(conn, "SELECT id FROM facturas WHERE id = ?", (factura_id,)):
            raise ValueError("Guarde la factura antes de adjuntar el soporte.")
        previo = fetch_one(conn, "SELECT id, ruta FROM soportes WHERE factura_id = ?", (factura_id,))
        if previo:
            conn.execute(
                "UPDATE soportes SET ruta=?, tamano=?, hash=?, nombre_original=? WHERE factura_id=?",
                (ruta_rel, tamano, digest, origen.name, factura_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO soportes (factura_id, ruta, tamano, hash, nombre_original)
                VALUES (?, ?, ?, ?, ?)
                """,
                (factura_id, ruta_rel, tamano, digest, origen.name),
            )
        _evento(conn, factura_id, "soporte", usuario["usuario"], ruta_rel)
    return {"ruta": ruta_rel, "tamano": tamano, "hash": digest}


def _comprimir_imagen(origen: Path, carpeta: Path) -> Path:
    try:
        from PIL import Image
    except ImportError as ex:
        raise ValueError("Falta Pillow para comprimir imágenes. Ejecute: python -m pip install pillow") from ex
    destino = carpeta / f"tmp-{secrets.token_hex(4)}.jpg"
    with Image.open(origen) as img:
        img.thumbnail((1600, 1600))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            destino = destino.with_suffix(".png")
            img.save(destino, "PNG", optimize=True)
            return destino
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(destino, "JPEG", quality=70, optimize=True)
    return destino


def copia_seguridad(destino: Path):
    destino = Path(destino)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta = destino / f"microempresa-el-mana-{stamp}"
    carpeta.mkdir(parents=True, exist_ok=False)
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, carpeta / "el_mana.db")
    if SOPORTES.exists():
        shutil.copytree(SOPORTES, carpeta / "soportes")
    return carpeta


def importar_excel(ruta: Path, usuario: dict):
    if not es_admin(usuario):
        raise ValueError("Solo el administrador puede importar el Excel.")
    try:
        import openpyxl
    except ImportError as ex:
        raise ValueError("Falta openpyxl. Ejecute: python -m pip install openpyxl") from ex
    wb = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        raise ValueError("El Excel está vacío.")
    headers = [_norm(c) for c in filas[0]]
    if _es_hoja_facturas(headers):
        return _importar_facturas_excel(filas, headers, usuario)
    if _es_hoja_semanal(headers):
        return _importar_cuentas_excel(filas, usuario)
    raise ValueError(
        "No reconozco el Excel. Para facturas use columnas: tipo, numero, fecha, nit, razon social, categoria, valor. "
        "Para la hoja semanal: FECHAS, INGRESO, GASTOS."
    )


def _norm(value):
    text = str(value or "").strip().lower()
    text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return re.sub(r"\s+", " ", text)


def _es_hoja_facturas(headers):
    unidos = " ".join(headers)
    return "nit" in unidos and ("numero" in unidos or "nro" in unidos)


def _es_hoja_semanal(headers):
    unidos = " ".join(headers)
    return "fecha" in unidos and ("ingreso" in unidos or "gasto" in unidos)


def _col(headers, *nombres):
    for i, h in enumerate(headers):
        if any(n in h for n in nombres):
            return i
    return None


def _importar_facturas_excel(filas, headers, usuario):
    idx = {
        "tipo": _col(headers, "tipo"),
        "numero": _col(headers, "numero", "nro", "factura"),
        "fecha": _col(headers, "fecha"),
        "nit": _col(headers, "nit", "cedula"),
        "razon": _col(headers, "razon", "tercero", "proveedor", "cliente"),
        "categoria": _col(headers, "categoria", "categoria"),
        "valor": _col(headers, "valor", "base", "antes"),
    }
    if None in (idx["tipo"], idx["numero"], idx["fecha"], idx["nit"], idx["razon"], idx["valor"]):
        raise ValueError("Faltan columnas obligatorias: tipo, numero, fecha, nit, razon social y valor.")
    ok = 0
    errores = []
    for n, row in enumerate(filas[1:], start=2):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        try:
            fecha = row[idx["fecha"]]
            if isinstance(fecha, datetime):
                fecha = fecha.strftime("%d/%m/%Y")
            categoria = "otros"
            if idx["categoria"] is not None and row[idx["categoria"]]:
                categoria = str(row[idx["categoria"]]).strip().lower()
            guardar_factura(
                {
                    "tipo": row[idx["tipo"]],
                    "numero": row[idx["numero"]],
                    "fecha": fecha,
                    "nit": row[idx["nit"]],
                    "razon_social": row[idx["razon"]],
                    "categoria": categoria,
                    "valor": row[idx["valor"]],
                },
                usuario,
            )
            ok += 1
        except (ValueError, sqlite3.IntegrityError) as ex:
            errores.append(f"Fila {n}: {ex}")
    return {"ok": ok, "errores": errores, "modo": "facturas"}


def _importar_cuentas_excel(filas, usuario):
    headers = [_norm(c) for c in filas[0]]
    i_fecha = _col(headers, "fecha")
    i_ing = _col(headers, "ingreso")
    i_gas = _col(headers, "gasto")
    sitio = "galeras"
    ok = 0
    with db() as conn:
        for row in filas[1:]:
            if not row:
                continue
            marca = _norm(row[0] if row[0] else "")
            if "galera" in marca:
                sitio = "galeras"
                continue
            if "since" in marca or "since" in marca or "sinc" in marca:
                sitio = "since"
                continue
            if i_fecha is None or row[i_fecha] in (None, ""):
                continue
            try:
                fecha = row[i_fecha]
                if isinstance(fecha, datetime):
                    fecha = fecha.date().isoformat()
                else:
                    fecha = _parse_fecha(str(fecha)).isoformat()
            except ValueError:
                continue
            ingreso = _num(row[i_ing] if i_ing is not None and i_ing < len(row) else 0)
            gastos = _num(row[i_gas] if i_gas is not None and i_gas < len(row) else 0)
            if ingreso == 0 and gastos == 0:
                continue
            guardar_cuenta(
                conn,
                {
                    "sitio": sitio,
                    "fecha": fecha,
                    "ingreso": ingreso,
                    "ingreso_esp": "Importado de Excel" if ingreso else "",
                    "gastos": gastos,
                    "gastos_esp": "Importado de Excel" if gastos else "",
                    "entradas": 0,
                    "entradas_esp": "",
                    "activos": 0,
                    "activos_esp": "",
                    "creditos": 0,
                    "creditos_esp": "",
                },
            )
            ok += 1
    return {"ok": ok, "errores": [], "modo": "cuentas semanales", "usuario": usuario["usuario"]}


def _num(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


def pedir_sesion():
    from database import init_db

    init_db()
    root = tk.Tk()
    root.title("Microempresa El Maná")
    root.geometry("420x280")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text="MICROEMPRESA EL MANÁ", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(frm, text="Inicie sesión para registrar y consultar facturas.").pack(anchor="w", pady=(0, 10))
    ttk.Label(frm, text="Usuario").pack(anchor="w")
    usuario = ttk.Entry(frm)
    usuario.insert(0, "admin")
    usuario.pack(fill="x", pady=(0, 6))
    ttk.Label(frm, text="Contraseña").pack(anchor="w")
    clave = ttk.Entry(frm, show="*")
    clave.pack(fill="x", pady=(0, 6))
    ttk.Label(frm, text="Primera vez: usuario admin, contraseña elmana.", foreground="#555").pack(anchor="w")
    sesion = {}

    def entrar(_event=None):
        user = autenticar(usuario.get(), clave.get())
        if not user:
            messagebox.showerror("Acceso", "Usuario o contraseña incorrectos.", parent=root)
            return
        sesion["user"] = user
        root.destroy()

    ttk.Button(frm, text="Entrar", command=entrar).pack(anchor="w", pady=12)
    clave.bind("<Return>", entrar)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return sesion.get("user")


class FacturasTab(ttk.Frame):
    def __init__(self, master, usuario, on_change=None):
        super().__init__(master, padding=8)
        self.usuario = usuario
        self.on_change = on_change
        self.edit_id = None
        self.pendiente = None
        self._build()
        self.buscar()

    def _build(self):
        ttk.Label(
            self,
            text="Facturas de compra y venta — soportes para la DIAN",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            self,
            text="El valor se escribe antes de IVA. El IVA y el total se calculan. El soporte (PDF, JPG o PNG, máx. 5 MB) se guarda por año y mes; en la base solo quedan la ruta, el tamaño y el hash.",
            wraplength=1200,
        ).pack(anchor="w", pady=(0, 6))

        form = ttk.LabelFrame(self, text="Registrar o editar", padding=8)
        form.pack(fill="x")
        grid = ttk.Frame(form)
        grid.pack(fill="x")
        self.tipo = ttk.Combobox(grid, values=list(TIPOS), state="readonly", width=12)
        self.tipo.set("compra")
        self.numero = ttk.Entry(grid, width=14)
        self.fecha = ttk.Entry(grid, width=12)
        self.fecha.insert(0, date.today().strftime("%d/%m/%Y"))
        self.nit = ttk.Entry(grid, width=16)
        self.razon = ttk.Entry(grid, width=28)
        self.categoria = ttk.Combobox(grid, values=list(CATEGORIAS), state="readonly", width=18)
        self.categoria.set("otros")
        self.valor = ttk.Entry(grid, width=12)
        self.pct = ttk.Entry(grid, width=6)
        self.pct.insert(0, str(get_iva_porcentaje()).replace(".0", ""))
        self.lbl_calc = ttk.Label(grid, text="IVA: 0    Total: 0")
        campos = [
            ("Tipo", self.tipo),
            ("Número", self.numero),
            ("Emisión", self.fecha),
            ("NIT o cédula", self.nit),
            ("Razón social", self.razon),
            ("Categoría", self.categoria),
            ("Valor antes de IVA", self.valor),
            ("% IVA", self.pct),
        ]
        for i, (texto, widget) in enumerate(campos):
            ttk.Label(grid, text=texto).grid(row=0, column=i, sticky="w", padx=3)
            widget.grid(row=1, column=i, padx=3, pady=2, sticky="w")
        self.lbl_calc.grid(row=2, column=0, columnspan=4, sticky="w", pady=4)
        self.valor.bind("<KeyRelease>", lambda _e: self._preview())
        self.pct.bind("<KeyRelease>", lambda _e: self._preview())
        botones = ttk.Frame(form)
        botones.pack(fill="x", pady=4)
        self.btn_guardar = ttk.Button(botones, text="Guardar factura", command=self.guardar)
        self.btn_guardar.pack(side="left", padx=2)
        ttk.Button(botones, text="Adjuntar soporte", command=self.adjuntar).pack(side="left", padx=2)
        ttk.Button(botones, text="Limpiar", command=self.limpiar).pack(side="left", padx=2)
        self.lbl_archivo = ttk.Label(botones, text="Sin soporte seleccionado")
        self.lbl_archivo.pack(side="left", padx=8)
        if not es_admin(self.usuario):
            self.btn_guardar.state(["disabled"])

        filtros = ttk.LabelFrame(self, text="Buscar", padding=8)
        filtros.pack(fill="x", pady=6)
        fg = ttk.Frame(filtros)
        fg.pack(fill="x")
        self.f_nit = ttk.Entry(fg, width=14)
        self.f_razon = ttk.Entry(fg, width=22)
        self.f_num = ttk.Entry(fg, width=12)
        self.f_desde = ttk.Entry(fg, width=12)
        self.f_hasta = ttk.Entry(fg, width=12)
        self.f_tipo = ttk.Combobox(fg, values=["", *TIPOS], width=10)
        self.f_cat = ttk.Combobox(fg, values=["", *CATEGORIAS], width=16)
        for i, (texto, widget) in enumerate(
            [
                ("NIT", self.f_nit),
                ("Razón social", self.f_razon),
                ("Número", self.f_num),
                ("Desde", self.f_desde),
                ("Hasta", self.f_hasta),
                ("Tipo", self.f_tipo),
                ("Categoría", self.f_cat),
            ]
        ):
            ttk.Label(fg, text=texto).grid(row=0, column=i, sticky="w", padx=3)
            widget.grid(row=1, column=i, padx=3)
        acc = ttk.Frame(filtros)
        acc.pack(fill="x", pady=6)
        ttk.Button(acc, text="Buscar", command=self.buscar).pack(side="left", padx=2)
        ttk.Button(acc, text="Reporte CSV (DIAN)", command=self.exportar).pack(side="left", padx=2)
        ttk.Button(acc, text="Editar seleccionada", command=self.cargar_edicion).pack(side="left", padx=2)
        ttk.Button(acc, text="Anular seleccionada", command=self.anular).pack(side="left", padx=2)
        ttk.Button(acc, text="Importar Excel", command=self.importar).pack(side="left", padx=2)
        ttk.Button(acc, text="Copia de seguridad", command=self.backup).pack(side="left", padx=2)

        self.lbl_totales = ttk.Label(self, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_totales.pack(anchor="w", pady=4)
        cols = ("tipo", "numero", "fecha", "nit", "razon", "categoria", "valor", "iva", "total", "estado", "soporte", "constancia")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        titulos = [
            ("tipo", "Tipo", 70),
            ("numero", "Número", 90),
            ("fecha", "Emisión", 90),
            ("nit", "NIT", 110),
            ("razon", "Razón social", 180),
            ("categoria", "Categoría", 120),
            ("valor", "Antes de IVA", 100),
            ("iva", "IVA", 80),
            ("total", "Total", 90),
            ("estado", "Estado", 70),
            ("soporte", "Soporte", 70),
            ("constancia", "Constancia", 220),
        ]
        for key, title, width in titulos:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width)
        self.tree.pack(fill="both", expand=True)

    def _preview(self):
        try:
            valor = float(self.valor.get().replace(",", "") or 0)
            pct = float(self.pct.get().replace(",", ".") or 0)
            iva = round(valor * pct / 100.0, 2)
            self.lbl_calc.config(text=f"IVA: {iva:,.0f}    Total: {valor + iva:,.0f}")
        except ValueError:
            self.lbl_calc.config(text="IVA: —    Total: —")

    def _filtros(self):
        return {
            "nit": self.f_nit.get(),
            "razon_social": self.f_razon.get(),
            "numero": self.f_num.get(),
            "desde": self.f_desde.get(),
            "hasta": self.f_hasta.get(),
            "tipo": self.f_tipo.get(),
            "categoria": self.f_cat.get(),
        }

    def buscar(self):
        try:
            filas = buscar_facturas(self._filtros())
        except ValueError as ex:
            messagebox.showerror("Búsqueda", str(ex), parent=self)
            return
        self._filas = filas
        for item in self.tree.get_children():
            self.tree.delete(item)
        for f in filas:
            constancia = f"Creó {f['creado_por']} {f['creado_en']}"
            if f["editado_por"]:
                constancia += f" | Editó {f['editado_por']} {f['editado_en']}"
            if f["anulado_por"]:
                constancia += f" | Anuló {f['anulado_por']} {f['anulado_en']}"
            self.tree.insert(
                "",
                "end",
                iid=str(f["id"]),
                values=(
                    f["tipo"],
                    f["numero"],
                    datetime.strptime(f["fecha_emision"], "%Y-%m-%d").strftime("%d/%m/%Y"),
                    f["nit"],
                    f["razon_social"],
                    f["categoria"],
                    f"{float(f['valor_antes_iva']):,.0f}",
                    f"{float(f['iva']):,.0f}",
                    f"{float(f['total']):,.0f}",
                    f["estado"],
                    "Sí" if f["soporte_ruta"] else "No",
                    constancia,
                ),
            )
        tot = totales_facturas(filas)
        self.lbl_totales.config(
            text=(
                f"Activas: {tot['cantidad']}   Anuladas: {tot['anuladas']}   "
                f"Ventas: {tot['ventas']:,.0f}   Compras: {tot['compras']:,.0f}   "
                f"IVA ventas: {tot['iva_ventas']:,.0f}   IVA compras: {tot['iva_compras']:,.0f}   "
                f"IVA a pagar: {tot['iva_a_pagar']:,.0f}"
            )
        )

    def guardar(self):
        data = {
            "tipo": self.tipo.get(),
            "numero": self.numero.get(),
            "fecha": self.fecha.get(),
            "nit": self.nit.get(),
            "razon_social": self.razon.get(),
            "categoria": self.categoria.get(),
            "valor": self.valor.get(),
            "iva_porcentaje": self.pct.get(),
        }
        try:
            fid = guardar_factura(data, self.usuario, self.edit_id)
            if self.pendiente:
                adjuntar_soporte(fid, self.pendiente, self.usuario)
                self.pendiente = None
            messagebox.showinfo("Factura", "Factura guardada.", parent=self)
            self.limpiar()
            self.buscar()
            if self.on_change:
                self.on_change()
        except (ValueError, sqlite3.IntegrityError) as ex:
            messagebox.showerror("Factura", str(ex), parent=self)

    def adjuntar(self):
        if not es_admin(self.usuario):
            messagebox.showinfo("Soporte", "Solo el administrador puede adjuntar soportes.", parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Adjuntar soporte",
            filetypes=[("Soportes", "*.pdf *.jpg *.jpeg *.png")],
        )
        if not path:
            return
        sel = self.tree.selection()
        if sel and not self.edit_id:
            try:
                info = adjuntar_soporte(int(sel[0]), Path(path), self.usuario)
                messagebox.showinfo("Soporte", f"Guardado.\nRuta: {info['ruta']}\nHash: {info['hash'][:16]}…", parent=self)
                self.buscar()
            except ValueError as ex:
                messagebox.showerror("Soporte", str(ex), parent=self)
            return
        self.pendiente = Path(path)
        self.lbl_archivo.config(text=f"Se adjuntará al guardar: {self.pendiente.name}")

    def cargar_edicion(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Editar", "Seleccione una factura.", parent=self)
            return
        fila = next(f for f in self._filas if str(f["id"]) == sel[0])
        if fila["estado"] != "activa":
            messagebox.showinfo("Editar", "La factura está anulada.", parent=self)
            return
        self.edit_id = fila["id"]
        self.tipo.set(fila["tipo"])
        self.numero.delete(0, "end")
        self.numero.insert(0, fila["numero"])
        self.fecha.delete(0, "end")
        self.fecha.insert(0, datetime.strptime(fila["fecha_emision"], "%Y-%m-%d").strftime("%d/%m/%Y"))
        self.nit.delete(0, "end")
        self.nit.insert(0, fila["nit"])
        self.razon.delete(0, "end")
        self.razon.insert(0, fila["razon_social"])
        self.categoria.set(fila["categoria"])
        self.valor.delete(0, "end")
        self.valor.insert(0, str(fila["valor_antes_iva"]))
        self.pct.delete(0, "end")
        self.pct.insert(0, str(fila["iva_porcentaje"]).replace(".0", ""))
        self._preview()
        self.btn_guardar.config(text="Guardar cambios")

    def anular(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Anular", "Seleccione una factura.", parent=self)
            return
        motivo = simpledialog.askstring("Anular factura", "Motivo de la anulación:", parent=self)
        if motivo is None:
            return
        try:
            anular_factura(int(sel[0]), self.usuario, motivo)
            self.buscar()
        except ValueError as ex:
            messagebox.showerror("Anular", str(ex), parent=self)

    def exportar(self):
        if not getattr(self, "_filas", None):
            self.buscar()
        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar reporte DIAN",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="reporte-facturas-dian.csv",
        )
        if not destino:
            return
        exportar_csv(self._filas, Path(destino))
        messagebox.showinfo("Reporte", f"CSV guardado en:\n{destino}", parent=self)

    def importar(self):
        path = filedialog.askopenfilename(parent=self, title="Importar Excel", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            res = importar_excel(Path(path), self.usuario)
        except ValueError as ex:
            messagebox.showerror("Importar", str(ex), parent=self)
            return
        extra = "\n".join(res["errores"][:8])
        messagebox.showinfo(
            "Importar",
            f"Modo: {res['modo']}\nRegistros importados: {res['ok']}\n{extra}",
            parent=self,
        )
        self.buscar()
        if self.on_change:
            self.on_change()

    def backup(self):
        if not es_admin(self.usuario):
            messagebox.showinfo("Copia", "Solo el administrador puede hacer la copia de seguridad.", parent=self)
            return
        destino = filedialog.askdirectory(parent=self, title="Carpeta destino de la copia")
        if not destino:
            return
        try:
            carpeta = copia_seguridad(Path(destino))
        except Exception as ex:
            messagebox.showerror("Copia", str(ex), parent=self)
            return
        messagebox.showinfo("Copia de seguridad", f"Copia lista en:\n{carpeta}", parent=self)

    def limpiar(self):
        self.edit_id = None
        self.pendiente = None
        self.numero.delete(0, "end")
        self.nit.delete(0, "end")
        self.razon.delete(0, "end")
        self.valor.delete(0, "end")
        self.lbl_archivo.config(text="Sin soporte seleccionado")
        self.btn_guardar.config(text="Guardar factura")
        self._preview()
