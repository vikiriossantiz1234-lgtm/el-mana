import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "el_mana.db"

# Hoja principal: cuentas semanales (Galeras = bananera, Sincé = distribución)
SITIO_GALERAS = "galeras"
SITIO_SINCE = "since"
SITIOS = (SITIO_GALERAS, SITIO_SINCE)

HOJA_CUENTAS_TITULO = "BANANERA EL MANÁ CUENTAS SEMANALES"

# Columnas iguales a la hoja de Excel
HOJA_CUENTAS_COLUMNAS = (
    ("fecha", "FECHAS"),
    ("ingreso", "INGRESO"),
    ("ingreso_esp", "ESPECIFICACIONES"),
    ("gastos", "GASTOS"),
    ("gastos_esp", "ESPECIFICACIONES"),
    ("entradas", "ENTRADAS"),
    ("entradas_esp", "ESPECIFICACIONES"),
    ("activos", "ACTIVOS"),
    ("activos_esp", "ESPECIFICACIONES"),
    ("creditos", "CREDITOS"),
    ("creditos_esp", "ESPECIFICACIONES"),
    ("iva_ingreso", "IVA ING."),
    ("iva_gastos", "IVA GST."),
    ("ganancias", "GANANCIAS"),
)

IVA_PORCENTAJE_DEFECTO = 19.0


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trabajadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                cedula TEXT UNIQUE,
                cargo TEXT DEFAULT 'Cosechador',
                tarifa_diaria REAL NOT NULL DEFAULT 0,
                telefono TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                fecha_ingreso TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS camiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                placa TEXT,
                conductor TEXT,
                cantidad_cajas REAL NOT NULL,
                precio_compra_caja REAL NOT NULL DEFAULT 0,
                notas TEXT,
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS salidas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                cantidad_cajas REAL NOT NULL,
                destino TEXT,
                precio_venta_caja REAL NOT NULL DEFAULT 0,
                camion_id INTEGER,
                notas TEXT,
                creado_en TEXT NOT NULL,
                FOREIGN KEY (camion_id) REFERENCES camiones(id)
            );

            CREATE TABLE IF NOT EXISTS asistencia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trabajador_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                presente INTEGER NOT NULL DEFAULT 1,
                motivo_ausencia TEXT,
                UNIQUE(trabajador_id, fecha),
                FOREIGN KEY (trabajador_id) REFERENCES trabajadores(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descripcion TEXT,
                monto REAL NOT NULL,
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trabajador_id INTEGER NOT NULL,
                periodo_inicio TEXT NOT NULL,
                periodo_fin TEXT NOT NULL,
                dias_trabajados INTEGER NOT NULL,
                monto REAL NOT NULL,
                pagado INTEGER NOT NULL DEFAULT 0,
                fecha_pago TEXT,
                notas TEXT,
                FOREIGN KEY (trabajador_id) REFERENCES trabajadores(id)
            );

            CREATE TABLE IF NOT EXISTS cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sitio TEXT NOT NULL CHECK(sitio IN ('galeras', 'since')),
                fecha TEXT NOT NULL,
                ingreso REAL NOT NULL DEFAULT 0,
                ingreso_esp TEXT,
                gastos REAL NOT NULL DEFAULT 0,
                gastos_esp TEXT,
                entradas REAL NOT NULL DEFAULT 0,
                entradas_esp TEXT,
                activos REAL NOT NULL DEFAULT 0,
                activos_esp TEXT,
                creditos REAL NOT NULL DEFAULT 0,
                creditos_esp TEXT,
                ganancias REAL NOT NULL DEFAULT 0,
                aplica_iva INTEGER NOT NULL DEFAULT 0,
                iva_porcentaje REAL NOT NULL DEFAULT 19,
                iva_ingreso REAL NOT NULL DEFAULT 0,
                iva_gastos REAL NOT NULL DEFAULT 0,
                referencia_tipo TEXT,
                referencia_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS config (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                rol TEXT NOT NULL CHECK(rol IN ('administrador', 'consulta')),
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS facturas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL CHECK(tipo IN ('compra', 'venta')),
                numero TEXT NOT NULL,
                fecha_emision TEXT NOT NULL,
                nit TEXT NOT NULL,
                razon_social TEXT NOT NULL,
                categoria TEXT NOT NULL,
                valor_antes_iva REAL NOT NULL,
                iva_porcentaje REAL NOT NULL,
                iva REAL NOT NULL,
                total REAL NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activa' CHECK(estado IN ('activa', 'anulada')),
                creado_por TEXT NOT NULL,
                creado_en TEXT NOT NULL,
                editado_por TEXT,
                editado_en TEXT,
                anulado_por TEXT,
                anulado_en TEXT,
                motivo_anulacion TEXT,
                UNIQUE(tipo, nit, numero)
            );

            CREATE TABLE IF NOT EXISTS soportes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id INTEGER NOT NULL UNIQUE,
                ruta TEXT NOT NULL,
                tamano INTEGER NOT NULL,
                hash TEXT NOT NULL,
                nombre_original TEXT,
                FOREIGN KEY (factura_id) REFERENCES facturas(id)
            );

            CREATE TABLE IF NOT EXISTS factura_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id INTEGER NOT NULL,
                accion TEXT NOT NULL,
                usuario TEXT NOT NULL,
                cuando TEXT NOT NULL,
                detalle TEXT,
                FOREIGN KEY (factura_id) REFERENCES facturas(id)
            );
            """
        )
        _asegurar_admin(conn)
        _migrate_schema(conn)


def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate_schema(conn):
    if not _column_exists(conn, "cuentas", "referencia_tipo"):
        conn.execute("ALTER TABLE cuentas ADD COLUMN referencia_tipo TEXT")
    if not _column_exists(conn, "cuentas", "referencia_id"):
        conn.execute("ALTER TABLE cuentas ADD COLUMN referencia_id INTEGER")
    if not _column_exists(conn, "camiones", "sitio"):
        conn.execute("ALTER TABLE camiones ADD COLUMN sitio TEXT NOT NULL DEFAULT 'galeras'")
    if not _column_exists(conn, "salidas", "sitio"):
        conn.execute("ALTER TABLE salidas ADD COLUMN sitio TEXT NOT NULL DEFAULT 'since'")
    if not _column_exists(conn, "gastos", "sitio"):
        conn.execute("ALTER TABLE gastos ADD COLUMN sitio TEXT DEFAULT 'galeras'")
    if not _column_exists(conn, "cuentas", "aplica_iva"):
        conn.execute("ALTER TABLE cuentas ADD COLUMN aplica_iva INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "cuentas", "iva_porcentaje"):
        conn.execute("ALTER TABLE cuentas ADD COLUMN iva_porcentaje REAL NOT NULL DEFAULT 19")
    if not _column_exists(conn, "cuentas", "iva_ingreso"):
        conn.execute("ALTER TABLE cuentas ADD COLUMN iva_ingreso REAL NOT NULL DEFAULT 0")
    if not _column_exists(conn, "cuentas", "iva_gastos"):
        conn.execute("ALTER TABLE cuentas ADD COLUMN iva_gastos REAL NOT NULL DEFAULT 0")
    conn.execute(
        "INSERT OR IGNORE INTO config (clave, valor) VALUES ('iva_porcentaje', ?)",
        (str(IVA_PORCENTAJE_DEFECTO),),
    )


def _iva_pct_conn(conn):
    row = fetch_one(conn, "SELECT valor FROM config WHERE clave = 'iva_porcentaje'")
    try:
        return float(row["valor"]) if row else IVA_PORCENTAJE_DEFECTO
    except (TypeError, ValueError):
        return IVA_PORCENTAJE_DEFECTO


def get_iva_porcentaje():
    with db() as conn:
        return _iva_pct_conn(conn)


def set_iva_porcentaje(valor):
    tasa = float(valor)
    if tasa < 0 or tasa > 100:
        raise ValueError("El IVA debe estar entre 0 y 100.")
    with db() as conn:
        conn.execute(
            "INSERT INTO config (clave, valor) VALUES ('iva_porcentaje', ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (str(tasa),),
        )


def calcular_iva(monto, porcentaje, aplica):
    if not aplica:
        return 0.0
    return round(float(monto or 0) * float(porcentaje or 0) / 100.0, 2)


def _asegurar_admin(conn):
    import hashlib
    import secrets

    row = fetch_one(conn, "SELECT id FROM usuarios LIMIT 1")
    if row:
        return
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", b"elmana", salt.encode(), 120_000).hex()
    conn.execute(
        """
        INSERT INTO usuarios (usuario, nombre, rol, salt, password_hash)
        VALUES ('admin', 'Propietario', 'administrador', ?, ?)
        """,
        (salt, digest),
    )


def today_iso():
    return date.today().isoformat()


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def fetch_one(conn, query, params=()):
    return conn.execute(query, params).fetchone()


def fetch_all(conn, query, params=()):
    return conn.execute(query, params).fetchall()


def inventario_actual(conn):
    row = fetch_one(
        conn,
        """
        SELECT
            COALESCE((SELECT SUM(cantidad_cajas) FROM camiones), 0)
            - COALESCE((SELECT SUM(cantidad_cajas) FROM salidas), 0) AS stock
        """,
    )
    return float(row["stock"] or 0)


def resumen_contable(conn, inicio=None, fin=None):
    """Resumen financiero; la hoja semanal (cuentas) es la fuente principal."""
    if inicio and fin:
        tg = totales_cuentas(conn, SITIO_GALERAS, inicio, fin)
        ts = totales_cuentas(conn, SITIO_SINCE, inicio, fin)
        valor_hoja = tg["total_cuentas"] + ts["total_cuentas"]
        gastos_hoja = tg["gasto_total"] + ts["gasto_total"]
        ingresos_hoja = tg["total_ingreso"] + ts["total_ingreso"]
        iva_cobrado = tg["iva_ingreso"] + ts["iva_ingreso"]
        iva_pagado = tg["iva_gastos"] + ts["iva_gastos"]
    else:
        valor_hoja = gastos_hoja = ingresos_hoja = iva_cobrado = iva_pagado = 0.0

    where_camiones = ""
    where_salidas = ""
    where_gastos = ""
    params = []

    if inicio and fin:
        where_camiones = "WHERE fecha BETWEEN ? AND ?"
        where_salidas = "WHERE fecha BETWEEN ? AND ?"
        where_gastos = "WHERE fecha BETWEEN ? AND ?"
        params = [inicio, fin]

    compras = fetch_one(
        conn,
        f"""
        SELECT COALESCE(SUM(cantidad_cajas * precio_compra_caja), 0) AS total
        FROM camiones {where_camiones}
        """,
        params,
    )["total"]

    ventas = fetch_one(
        conn,
        f"""
        SELECT
            COALESCE(SUM(cantidad_cajas * precio_venta_caja), 0) AS total,
            COALESCE(SUM(cantidad_cajas), 0) AS cajas
        FROM salidas {where_salidas}
        """,
        params,
    )

    gastos = fetch_one(
        conn,
        f"""
        SELECT COALESCE(SUM(monto), 0) AS total
        FROM gastos {where_gastos}
        """,
        params,
    )["total"]

    nomina_pagada = fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(monto), 0) AS total
        FROM pagos WHERE pagado = 1
        """
        + (" AND fecha_pago BETWEEN ? AND ?" if inicio and fin else ""),
        [inicio, fin] if inicio and fin else [],
    )["total"]

    nomina_pendiente = fetch_one(
        conn,
        "SELECT COALESCE(SUM(monto), 0) AS total FROM pagos WHERE pagado = 0",
    )["total"]

    ingresos = float(ventas["total"] or 0)
    egresos = float(compras or 0) + float(gastos or 0) + float(nomina_pagada or 0)
    valor_neto = ingresos - egresos

    return {
        "compras": float(compras or 0),
        "ventas": ingresos,
        "cajas_vendidas": float(ventas["cajas"] or 0),
        "gastos": float(gastos or 0),
        "nomina_pagada": float(nomina_pagada or 0),
        "nomina_pendiente": float(nomina_pendiente or 0),
        "ingresos": ingresos,
        "egresos": egresos,
        "valor_neto": valor_neto,
        "inventario": inventario_actual(conn),
        "hoja_ingresos": ingresos_hoja,
        "hoja_gastos": gastos_hoja,
        "hoja_valor_neto": valor_hoja if inicio and fin else valor_neto,
        "iva_cobrado": iva_cobrado,
        "iva_pagado": iva_pagado,
        "iva_a_pagar": iva_cobrado - iva_pagado,
        "iva_porcentaje": _iva_pct_conn(conn),
    }


def calcular_nomina_trabajador(conn, trabajador_id, inicio, fin):
    worker = fetch_one(conn, "SELECT * FROM trabajadores WHERE id = ?", (trabajador_id,))
    if not worker:
        return None

    row = fetch_one(
        conn,
        """
        SELECT COUNT(*) AS dias
        FROM asistencia
        WHERE trabajador_id = ? AND presente = 1 AND fecha BETWEEN ? AND ?
        """,
        (trabajador_id, inicio, fin),
    )
    dias = int(row["dias"] or 0)
    monto = dias * float(worker["tarifa_diaria"])
    return {"dias_trabajados": dias, "monto": monto, "tarifa_diaria": float(worker["tarifa_diaria"])}


def calcular_ganancia_fila(ingreso, gastos, entradas, activos, creditos):
    return (
        float(ingreso or 0)
        - float(gastos or 0)
        + float(entradas or 0)
        + float(activos or 0)
        - float(creditos or 0)
    )


def listar_cuentas(conn, sitio, inicio, fin):
    return fetch_all(
        conn,
        """
        SELECT * FROM cuentas
        WHERE sitio = ? AND fecha BETWEEN ? AND ?
        ORDER BY fecha ASC, id ASC
        """,
        (sitio, inicio, fin),
    )


def totales_cuentas(conn, sitio, inicio, fin):
    row = fetch_one(
        conn,
        """
        SELECT
            COALESCE(SUM(gastos), 0) AS gasto_total,
            COALESCE(SUM(ganancias), 0) AS total_cuentas,
            COALESCE(SUM(ingreso), 0) AS total_ingreso,
            COALESCE(SUM(entradas), 0) AS total_entradas,
            COALESCE(SUM(iva_ingreso), 0) AS iva_ingreso,
            COALESCE(SUM(iva_gastos), 0) AS iva_gastos
        FROM cuentas
        WHERE sitio = ? AND fecha BETWEEN ? AND ?
        """,
        (sitio, inicio, fin),
    )
    return {
        "gasto_total": float(row["gasto_total"] or 0),
        "total_cuentas": float(row["total_cuentas"] or 0),
        "total_ingreso": float(row["total_ingreso"] or 0),
        "total_entradas": float(row["total_entradas"] or 0),
        "iva_ingreso": float(row["iva_ingreso"] or 0),
        "iva_gastos": float(row["iva_gastos"] or 0),
        "iva_a_pagar": float(row["iva_ingreso"] or 0) - float(row["iva_gastos"] or 0),
    }


def guardar_cuenta(conn, data):
    gan = calcular_ganancia_fila(
        data["ingreso"],
        data["gastos"],
        data["entradas"],
        data["activos"],
        data["creditos"],
    )
    aplica = 1 if data.get("aplica_iva") else 0
    pct = data.get("iva_porcentaje")
    if pct is None:
        pct = _iva_pct_conn(conn)
    iva_ing = calcular_iva(data["ingreso"], pct, aplica)
    iva_gst = calcular_iva(data["gastos"], pct, aplica)
    if data.get("id"):
        conn.execute(
            """
            UPDATE cuentas SET
                sitio = ?, fecha = ?, ingreso = ?, ingreso_esp = ?, gastos = ?, gastos_esp = ?,
                entradas = ?, entradas_esp = ?, activos = ?, activos_esp = ?,
                creditos = ?, creditos_esp = ?, ganancias = ?,
                aplica_iva = ?, iva_porcentaje = ?, iva_ingreso = ?, iva_gastos = ?,
                referencia_tipo = ?, referencia_id = ?
            WHERE id = ?
            """,
            (
                data["sitio"],
                data["fecha"],
                data["ingreso"],
                data.get("ingreso_esp"),
                data["gastos"],
                data.get("gastos_esp"),
                data["entradas"],
                data.get("entradas_esp"),
                data["activos"],
                data.get("activos_esp"),
                data["creditos"],
                data.get("creditos_esp"),
                gan,
                aplica,
                pct,
                iva_ing,
                iva_gst,
                data.get("referencia_tipo"),
                data.get("referencia_id"),
                data["id"],
            ),
        )
        return data["id"]

    cur = conn.execute(
        """
        INSERT INTO cuentas (
            sitio, fecha, ingreso, ingreso_esp, gastos, gastos_esp,
            entradas, entradas_esp, activos, activos_esp, creditos, creditos_esp, ganancias,
            aplica_iva, iva_porcentaje, iva_ingreso, iva_gastos,
            referencia_tipo, referencia_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["sitio"],
            data["fecha"],
            data["ingreso"],
            data.get("ingreso_esp"),
            data["gastos"],
            data.get("gastos_esp"),
            data["entradas"],
            data.get("entradas_esp"),
            data["activos"],
            data.get("activos_esp"),
            data["creditos"],
            data.get("creditos_esp"),
            gan,
            aplica,
            pct,
            iva_ing,
            iva_gst,
            data.get("referencia_tipo"),
            data.get("referencia_id"),
        ),
    )
    return cur.lastrowid


def eliminar_cuenta(conn, cuenta_id):
    conn.execute("DELETE FROM cuentas WHERE id = ?", (cuenta_id,))


def obtener_cuenta(conn, cuenta_id):
    return fetch_one(conn, "SELECT * FROM cuentas WHERE id = ?", (cuenta_id,))


def _bloque_hoja(conn, sitio, inicio, fin):
    nombre = "GALERAS" if sitio == SITIO_GALERAS else "SINCÉ"
    totales = totales_cuentas(conn, sitio, inicio, fin)
    return {
        "sitio": sitio,
        "nombre": nombre,
        "filas": listar_cuentas(conn, sitio, inicio, fin),
        "totales": totales,
    }


def obtener_hoja_semanal(inicio, fin):
    """Datos completos de la hoja semanal para la aplicación principal."""
    with db() as conn:
        galeras = _bloque_hoja(conn, SITIO_GALERAS, inicio, fin)
        since = _bloque_hoja(conn, SITIO_SINCE, inicio, fin)
        return {
            "titulo": HOJA_CUENTAS_TITULO,
            "columnas": HOJA_CUENTAS_COLUMNAS,
            "inicio": inicio,
            "fin": fin,
            "galeras": galeras,
            "since": since,
            "consolidado": {
                "gasto_total": galeras["totales"]["gasto_total"] + since["totales"]["gasto_total"],
                "total_cuentas": galeras["totales"]["total_cuentas"] + since["totales"]["total_cuentas"],
                "total_ingreso": galeras["totales"]["total_ingreso"] + since["totales"]["total_ingreso"],
                "iva_cobrado": galeras["totales"]["iva_ingreso"] + since["totales"]["iva_ingreso"],
                "iva_pagado": galeras["totales"]["iva_gastos"] + since["totales"]["iva_gastos"],
                "iva_a_pagar": (
                    galeras["totales"]["iva_ingreso"]
                    + since["totales"]["iva_ingreso"]
                    - galeras["totales"]["iva_gastos"]
                    - since["totales"]["iva_gastos"]
                ),
            },
        }


def _sync_cuenta_camion(conn, camion_id, fecha, placa, cajas, precio):
    total_compra = cajas * precio if precio else 0
    guardar_cuenta(
        conn,
        {
            "sitio": SITIO_GALERAS,
            "fecha": fecha,
            "ingreso": 0,
            "ingreso_esp": "",
            "gastos": total_compra,
            "gastos_esp": f"Compra camión {placa or '—'}",
            "entradas": cajas,
            "entradas_esp": f"Llegada camión {placa or ''}".strip(),
            "activos": 0,
            "activos_esp": "",
            "creditos": 0,
            "creditos_esp": "",
            "referencia_tipo": "camion",
            "referencia_id": camion_id,
        },
    )


def registrar_camion(fecha, placa, conductor, cantidad_cajas, precio_compra_caja, sync_hoja=True):
    if cantidad_cajas <= 0:
        raise ValueError("La cantidad de cajas debe ser mayor a cero.")
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO camiones (fecha, placa, conductor, cantidad_cajas, precio_compra_caja, notas, creado_en, sitio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fecha, placa, conductor, cantidad_cajas, precio_compra_caja, "", now_iso(), SITIO_GALERAS),
        )
        camion_id = cur.lastrowid
        if sync_hoja:
            _sync_cuenta_camion(conn, camion_id, fecha, placa, cantidad_cajas, precio_compra_caja)
        return camion_id


def listar_camiones(limite=80):
    with db() as conn:
        return fetch_all(
            conn,
            "SELECT * FROM camiones ORDER BY fecha DESC, id DESC LIMIT ?",
            (limite,),
        )


def _sync_cuenta_salida(conn, salida_id, fecha, destino, cantidad, precio, sitio):
    total = cantidad * precio if precio else 0
    guardar_cuenta(
        conn,
        {
            "sitio": sitio,
            "fecha": fecha,
            "ingreso": total,
            "ingreso_esp": destino or "Venta del día",
            "gastos": 0,
            "gastos_esp": "",
            "entradas": cantidad if sitio == SITIO_GALERAS else 0,
            "entradas_esp": "Despacho" if cantidad and sitio == SITIO_GALERAS else "",
            "activos": 0,
            "activos_esp": "",
            "creditos": 0,
            "creditos_esp": "",
            "aplica_iva": True,
            "referencia_tipo": "salida",
            "referencia_id": salida_id,
        },
    )


def registrar_salida(fecha, cantidad_cajas, destino, precio_venta_caja, sitio=SITIO_SINCE, sync_hoja=True):
    if cantidad_cajas <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    with db() as conn:
        stock = inventario_actual(conn)
        if cantidad_cajas > stock:
            raise ValueError(f"Inventario insuficiente. Disponible: {stock:,.0f} cajas.")
        cur = conn.execute(
            """
            INSERT INTO salidas (fecha, cantidad_cajas, destino, precio_venta_caja, camion_id, notas, creado_en, sitio)
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (fecha, cantidad_cajas, destino, precio_venta_caja, "", now_iso(), sitio),
        )
        salida_id = cur.lastrowid
        if sync_hoja:
            _sync_cuenta_salida(conn, salida_id, fecha, destino, cantidad_cajas, precio_venta_caja, sitio)
        return salida_id


def registrar_venta_dia_since(fecha, monto, especificacion="Venta del día"):
    with db() as conn:
        return guardar_cuenta(
            conn,
            {
                "sitio": SITIO_SINCE,
                "fecha": fecha,
                "ingreso": monto,
                "ingreso_esp": especificacion,
                "aplica_iva": True,
                "gastos": 0,
                "gastos_esp": "",
                "entradas": 0,
                "entradas_esp": "",
                "activos": 0,
                "activos_esp": "",
                "creditos": 0,
                "creditos_esp": "",
                "referencia_tipo": "manual",
                "referencia_id": None,
            },
        )


def crear_trabajador(nombre, tarifa_diaria, cargo="Cosechador", cedula="", telefono=""):
    if not nombre.strip():
        raise ValueError("El nombre es obligatorio.")
    with db() as conn:
        conn.execute(
            """
            INSERT INTO trabajadores (nombre, cedula, cargo, tarifa_diaria, telefono, fecha_ingreso)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nombre.strip(), cedula, cargo, tarifa_diaria, telefono, today_iso()),
        )


def listar_trabajadores():
    with db() as conn:
        return fetch_all(
            conn,
            """
            SELECT * FROM trabajadores
            ORDER BY CASE cargo WHEN 'Jefe' THEN 0 ELSE 1 END, activo DESC, nombre
            """,
        )


def toggle_trabajador(worker_id):
    with db() as conn:
        conn.execute(
            "UPDATE trabajadores SET activo = CASE WHEN activo = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (worker_id,),
        )


def nombre_jefe():
    with db() as conn:
        row = fetch_one(
            conn,
            "SELECT nombre FROM trabajadores WHERE cargo = 'Jefe' AND activo = 1 ORDER BY id LIMIT 1",
        )
        return row["nombre"] if row else "Sin registrar"


def listar_pagos():
    with db() as conn:
        return fetch_all(
            conn,
            """
            SELECT p.*, t.nombre AS trabajador_nombre, t.cargo
            FROM pagos p
            JOIN trabajadores t ON t.id = p.trabajador_id
            ORDER BY p.pagado ASC, p.periodo_fin DESC, t.nombre
            """,
        )


def marcar_pago(pago_id):
    with db() as conn:
        conn.execute(
            "UPDATE pagos SET pagado = 1, fecha_pago = ? WHERE id = ?",
            (today_iso(), pago_id),
        )


def listar_asistencia(fecha):
    with db() as conn:
        workers = fetch_all(
            conn,
            """
            SELECT * FROM trabajadores WHERE activo = 1
            ORDER BY CASE cargo WHEN 'Jefe' THEN 0 ELSE 1 END, nombre
            """,
        )
        registros = {
            row["trabajador_id"]: row
            for row in fetch_all(conn, "SELECT * FROM asistencia WHERE fecha = ?", (fecha,))
        }
        resumen = fetch_one(
            conn,
            """
            SELECT
                COALESCE(SUM(CASE WHEN presente = 1 THEN 1 ELSE 0 END), 0) AS presentes,
                COALESCE(SUM(CASE WHEN presente = 0 THEN 1 ELSE 0 END), 0) AS ausentes
            FROM asistencia WHERE fecha = ?
            """,
            (fecha,),
        )
        return workers, registros, resumen


def guardar_asistencia(fecha, items):
    with db() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO asistencia (trabajador_id, fecha, presente, motivo_ausencia)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(trabajador_id, fecha) DO UPDATE SET
                    presente = excluded.presente,
                    motivo_ausencia = excluded.motivo_ausencia
                """,
                (
                    item["trabajador_id"],
                    fecha,
                    1 if item.get("presente") else 0,
                    item.get("motivo") if not item.get("presente") else None,
                ),
            )


def listar_salidas(limite=80):
    with db() as conn:
        return fetch_all(
            conn,
            "SELECT * FROM salidas ORDER BY fecha DESC, id DESC LIMIT ?",
            (limite,),
        )


def resumen_app(inicio, fin):
    with db() as conn:
        return resumen_contable(conn, inicio, fin)


def marcar_asistencia_dia(fecha, presente=True):
    with db() as conn:
        workers = fetch_all(conn, "SELECT id FROM trabajadores WHERE activo = 1")
        for w in workers:
            conn.execute(
                """
                INSERT INTO asistencia (trabajador_id, fecha, presente, motivo_ausencia)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT(trabajador_id, fecha) DO UPDATE SET presente = excluded.presente, motivo_ausencia = NULL
                """,
                (w["id"], fecha, 1 if presente else 0),
            )


def generar_nomina_semana(inicio, fin, sync_hoja=True):
    generados = 0
    total = 0.0
    with db() as conn:
        workers = fetch_all(conn, "SELECT id, nombre FROM trabajadores WHERE activo = 1")
        for w in workers:
            nom = calcular_nomina_trabajador(conn, w["id"], inicio, fin)
            if not nom or nom["dias_trabajados"] <= 0:
                continue
            exists = fetch_one(
                conn,
                "SELECT id FROM pagos WHERE trabajador_id = ? AND periodo_inicio = ? AND periodo_fin = ?",
                (w["id"], inicio, fin),
            )
            if exists:
                continue
            cur = conn.execute(
                """
                INSERT INTO pagos (trabajador_id, periodo_inicio, periodo_fin, dias_trabajados, monto, pagado)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (w["id"], inicio, fin, nom["dias_trabajados"], nom["monto"]),
            )
            pago_id = cur.lastrowid
            if sync_hoja:
                guardar_cuenta(
                    conn,
                    {
                        "sitio": SITIO_GALERAS,
                        "fecha": fin,
                        "ingreso": 0,
                        "ingreso_esp": "",
                        "gastos": nom["monto"],
                        "gastos_esp": f"Pago {w['nombre']} ({nom['dias_trabajados']} días)",
                        "entradas": 0,
                        "entradas_esp": "",
                        "activos": 0,
                        "activos_esp": "",
                        "creditos": 0,
                        "creditos_esp": "",
                        "referencia_tipo": "pago",
                        "referencia_id": pago_id,
                    },
                )
            generados += 1
            total += nom["monto"]
    return {"generados": generados, "total": total}
