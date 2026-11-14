/**
 * EL MANA - Bananera
 * Google Apps Script + Google Sheets
 *
 * PASOS PARA CREARLA EN GOOGLE:
 * 1. Ve a https://sheets.google.com y crea una hoja nueva llamada "El Mana"
 * 2. Menú Extensiones → Apps Script
 * 3. Borra el contenido de Code.gs y pega TODO el contenido de este archivo
 * 4. Crea archivos HTML: clic + → HTML → nombra "Index" y pega Index.html
 * 5. Guarda (Ctrl+S), ejecuta la función "setup" (autoriza permisos la primera vez)
 * 6. Implementar → Nueva implementación → Tipo: App web
 *    - Ejecutar como: Yo
 *    - Quién tiene acceso: Cualquier persona con cuenta de Google (o tu organización)
 * 7. Copia la URL que te da Google — esa es tu app, ábrela desde celular o PC
 */

const SHEETS = {
  TRABAJADORES: 'Trabajadores',
  CAMIONES: 'Camiones',
  SALIDAS: 'Salidas',
  ASISTENCIA: 'Asistencia',
  GASTOS: 'Gastos',
  PAGOS: 'Pagos',
};

function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  ensureSheet_(ss, SHEETS.TRABAJADORES, [
    'id', 'nombre', 'cedula', 'cargo', 'tarifa_diaria', 'telefono', 'activo', 'fecha_ingreso',
  ]);
  ensureSheet_(ss, SHEETS.CAMIONES, [
    'id', 'fecha', 'placa', 'conductor', 'cantidad_cajas', 'precio_compra_caja', 'notas', 'creado_en',
  ]);
  ensureSheet_(ss, SHEETS.SALIDAS, [
    'id', 'fecha', 'cantidad_cajas', 'destino', 'precio_venta_caja', 'camion_id', 'notas', 'creado_en',
  ]);
  ensureSheet_(ss, SHEETS.ASISTENCIA, [
    'id', 'trabajador_id', 'fecha', 'presente', 'motivo_ausencia',
  ]);
  ensureSheet_(ss, SHEETS.GASTOS, [
    'id', 'fecha', 'categoria', 'descripcion', 'monto', 'creado_en',
  ]);
  ensureSheet_(ss, SHEETS.PAGOS, [
    'id', 'trabajador_id', 'periodo_inicio', 'periodo_fin', 'dias_trabajados', 'monto', 'pagado', 'fecha_pago',
  ]);

  SpreadsheetApp.getUi().alert(
    'El Mana listo',
    'Hojas creadas. Ahora publica la app web:\nImplementar → Nueva implementación → App web',
    SpreadsheetApp.getUi().ButtonSet.OK,
  );
}

function ensureSheet_(ss, name, headers) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
}

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('El Mana - Bananera')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('El Mana')
    .addItem('Configurar hojas', 'setup')
    .addItem('Abrir app web', 'abrirApp')
    .addToUi();
}

function abrirApp() {
  const url = ScriptApp.getService().getUrl();
  if (!url) {
    SpreadsheetApp.getUi().alert('Primero publica la app: Implementar → Nueva implementación → App web');
    return;
  }
  const html = HtmlService.createHtmlOutput(
    '<p>Abre este enlace:</p><a href="' + url + '" target="_blank">' + url + '</a>',
  ).setWidth(420).setHeight(100);
  SpreadsheetApp.getUi().showModalDialog(html, 'URL de El Mana');
}

// --- API para la interfaz web ---

function getDashboard() {
  const resumen = resumenContable_();
  const camiones = getRows_(SHEETS.CAMIONES).slice(-5).reverse();
  const trabajadores = getRows_(SHEETS.TRABAJADORES).filter(function (t) {
    return t.activo === '1' || t.activo === 1 || t.activo === true;
  });
  const hoy = today_();
  const asistencia = getRows_(SHEETS.ASISTENCIA).filter(function (a) {
    return a.fecha === hoy && (a.presente === '0' || a.presente === 0 || a.presente === false);
  });
  const trabMap = {};
  getRows_(SHEETS.TRABAJADORES).forEach(function (t) {
    trabMap[t.id] = t.nombre;
  });
  const ausentes = asistencia.map(function (a) {
    return { nombre: trabMap[a.trabajador_id] || 'Desconocido', motivo: a.motivo_ausencia || '' };
  });
  return { resumen: resumen, camiones: camiones, trabajadoresActivos: trabajadores.length, ausentes: ausentes, hoy: hoy };
}

function getCamiones() {
  return {
    registros: getRows_(SHEETS.CAMIONES).reverse(),
    total: sumField_(SHEETS.CAMIONES, 'cantidad_cajas'),
  };
}

function registrarCamion(data) {
  const cantidad = parseFloat(data.cantidad_cajas);
  if (!cantidad || cantidad <= 0) throw new Error('La cantidad debe ser mayor a cero.');
  appendRow_(SHEETS.CAMIONES, {
    id: nextId_(SHEETS.CAMIONES),
    fecha: data.fecha || today_(),
    placa: data.placa || '',
    conductor: data.conductor || '',
    cantidad_cajas: cantidad,
    precio_compra_caja: parseFloat(data.precio_compra_caja) || 0,
    notas: data.notas || '',
    creado_en: now_(),
  });
  return { ok: true };
}

function getSalidas() {
  const inventario = inventario_();
  const camiones = getRows_(SHEETS.CAMIONES).slice(-50).reverse();
  return {
    registros: getRows_(SHEETS.SALIDAS).reverse(),
    inventario: inventario,
    camiones: camiones,
  };
}

function registrarSalida(data) {
  const cantidad = parseFloat(data.cantidad_cajas);
  const inventario = inventario_();
  if (!cantidad || cantidad <= 0) throw new Error('La cantidad debe ser mayor a cero.');
  if (cantidad > inventario) throw new Error('Inventario insuficiente. Disponible: ' + inventario + ' cajas.');
  appendRow_(SHEETS.SALIDAS, {
    id: nextId_(SHEETS.SALIDAS),
    fecha: data.fecha || today_(),
    cantidad_cajas: cantidad,
    destino: data.destino || '',
    precio_venta_caja: parseFloat(data.precio_venta_caja) || 0,
    camion_id: data.camion_id || '',
    notas: data.notas || '',
    creado_en: now_(),
  });
  return { ok: true };
}

function getTrabajadores() {
  return getRows_(SHEETS.TRABAJADORES);
}

function crearTrabajador(data) {
  if (!data.nombre || !data.nombre.trim()) throw new Error('El nombre es obligatorio.');
  appendRow_(SHEETS.TRABAJADORES, {
    id: nextId_(SHEETS.TRABAJADORES),
    nombre: data.nombre.trim(),
    cedula: data.cedula || '',
    cargo: data.cargo || 'Cosechador',
    tarifa_diaria: parseFloat(data.tarifa_diaria) || 0,
    telefono: data.telefono || '',
    activo: '1',
    fecha_ingreso: today_(),
  });
  return { ok: true };
}

function toggleTrabajador(id) {
  const sheet = getSheet_(SHEETS.TRABAJADORES);
  const rows = sheet.getDataRange().getValues();
  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(id)) {
      const actual = String(rows[i][6]);
      sheet.getRange(i + 1, 7).setValue(actual === '1' ? '0' : '1');
      return { ok: true };
    }
  }
  throw new Error('Trabajador no encontrado.');
}

function getAsistencia(fecha) {
  fecha = fecha || today_();
  const trabajadores = getRows_(SHEETS.TRABAJADORES).filter(function (t) {
    return t.activo === '1' || t.activo === 1 || t.activo === true;
  });
  const registros = getRows_(SHEETS.ASISTENCIA).filter(function (a) {
    return a.fecha === fecha;
  });
  const map = {};
  registros.forEach(function (r) {
    map[r.trabajador_id] = r;
  });
  let presentes = 0;
  let ausentes = 0;
  registros.forEach(function (r) {
    if (r.presente === '1' || r.presente === 1 || r.presente === true) presentes++;
    else ausentes++;
  });
  return { fecha: fecha, trabajadores: trabajadores, registros: map, presentes: presentes, ausentes: ausentes };
}

function guardarAsistencia(fecha, items) {
  const sheet = getSheet_(SHEETS.ASISTENCIA);
  const existing = getRows_(SHEETS.ASISTENCIA);
  items.forEach(function (item) {
    const found = existing.find(function (e) {
      return String(e.trabajador_id) === String(item.trabajador_id) && e.fecha === fecha;
    });
    if (found) {
      updateRowById_(SHEETS.ASISTENCIA, found.id, {
        presente: item.presente ? '1' : '0',
        motivo_ausencia: item.presente ? '' : (item.motivo || ''),
      });
    } else {
      appendRow_(SHEETS.ASISTENCIA, {
        id: nextId_(SHEETS.ASISTENCIA),
        trabajador_id: item.trabajador_id,
        fecha: fecha,
        presente: item.presente ? '1' : '0',
        motivo_ausencia: item.presente ? '' : (item.motivo || ''),
      });
    }
  });
  return { ok: true };
}

function getPagos() {
  const pagos = getRows_(SHEETS.PAGOS);
  const trab = {};
  getRows_(SHEETS.TRABAJADORES).forEach(function (t) {
    trab[t.id] = t;
  });
  const lista = pagos.map(function (p) {
    const t = trab[p.trabajador_id] || {};
    return Object.assign({}, p, { trabajador_nombre: t.nombre || '', cargo: t.cargo || '' });
  }).reverse();
  let pendiente = 0;
  let pagado = 0;
  pagos.forEach(function (p) {
    const m = parseFloat(p.monto) || 0;
    if (p.pagado === '1' || p.pagado === 1) pagado += m;
    else pendiente += m;
  });
  const hoy = new Date();
  return {
    pagos: lista,
    totalPendiente: pendiente,
    totalPagado: pagado,
    inicioDefault: formatDate_(new Date(hoy.getFullYear(), hoy.getMonth(), 1)),
    finDefault: today_(),
  };
}

function generarNomina(inicio, fin) {
  const trabajadores = getRows_(SHEETS.TRABAJADORES).filter(function (t) {
    return t.activo === '1' || t.activo === 1;
  });
  const asistencia = getRows_(SHEETS.ASISTENCIA);
  const pagos = getRows_(SHEETS.PAGOS);
  let generados = 0;
  trabajadores.forEach(function (t) {
    const dias = asistencia.filter(function (a) {
      return (
        String(a.trabajador_id) === String(t.id) &&
        a.fecha >= inicio &&
        a.fecha <= fin &&
        (a.presente === '1' || a.presente === 1 || a.presente === true)
      );
    }).length;
    if (dias <= 0) return;
    const exists = pagos.some(function (p) {
      return String(p.trabajador_id) === String(t.id) && p.periodo_inicio === inicio && p.periodo_fin === fin;
    });
    if (exists) return;
    const monto = dias * (parseFloat(t.tarifa_diaria) || 0);
    appendRow_(SHEETS.PAGOS, {
      id: nextId_(SHEETS.PAGOS),
      trabajador_id: t.id,
      periodo_inicio: inicio,
      periodo_fin: fin,
      dias_trabajados: dias,
      monto: monto,
      pagado: '0',
      fecha_pago: '',
    });
    generados++;
  });
  return { ok: true, generados: generados };
}

function marcarPagado(pagoId) {
  updateRowById_(SHEETS.PAGOS, pagoId, { pagado: '1', fecha_pago: today_() });
  return { ok: true };
}

function getContabilidad(inicio, fin) {
  inicio = inicio || formatDate_(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  fin = fin || today_();
  const resumen = resumenContable_(inicio, fin);
  const gastos = getRows_(SHEETS.GASTOS).filter(function (g) {
    return g.fecha >= inicio && g.fecha <= fin;
  }).reverse();
  const movimientos = [];
  getRows_(SHEETS.SALIDAS).forEach(function (s) {
    if (s.fecha >= inicio && s.fecha <= fin) {
      movimientos.push({
        fecha: s.fecha,
        tipo: 'Venta',
        detalle: s.destino || '',
        cajas: s.cantidad_cajas,
        monto: (parseFloat(s.cantidad_cajas) || 0) * (parseFloat(s.precio_venta_caja) || 0),
      });
    }
  });
  getRows_(SHEETS.CAMIONES).forEach(function (c) {
    if (c.fecha >= inicio && c.fecha <= fin) {
      movimientos.push({
        fecha: c.fecha,
        tipo: 'Compra banano',
        detalle: c.placa || '',
        cajas: c.cantidad_cajas,
        monto: (parseFloat(c.cantidad_cajas) || 0) * (parseFloat(c.precio_compra_caja) || 0),
      });
    }
  });
  gastos.forEach(function (g) {
    movimientos.push({ fecha: g.fecha, tipo: 'Gasto', detalle: g.categoria, cajas: '', monto: g.monto });
  });
  movimientos.sort(function (a, b) {
    return a.fecha < b.fecha ? 1 : -1;
  });
  return { resumen: resumen, gastos: gastos, movimientos: movimientos, inicio: inicio, fin: fin };
}

function registrarGasto(data) {
  const monto = parseFloat(data.monto);
  if (!monto || monto <= 0) throw new Error('El monto debe ser mayor a cero.');
  appendRow_(SHEETS.GASTOS, {
    id: nextId_(SHEETS.GASTOS),
    fecha: data.fecha || today_(),
    categoria: data.categoria || 'Otro',
    descripcion: data.descripcion || '',
    monto: monto,
    creado_en: now_(),
  });
  return { ok: true };
}

// --- Helpers ---

function getSheet_(name) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
}

function getHeaders_(name) {
  const sheet = getSheet_(name);
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
}

function getRows_(name) {
  const sheet = getSheet_(name);
  if (sheet.getLastRow() <= 1) return [];
  const headers = getHeaders_(name);
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, headers.length).getValues();
  return values.map(function (row) {
    const obj = {};
    headers.forEach(function (h, i) {
      obj[h] = row[i] instanceof Date ? formatDate_(row[i]) : row[i];
    });
    return obj;
  });
}

function appendRow_(name, obj) {
  const headers = getHeaders_(name);
  const row = headers.map(function (h) {
    return obj[h] !== undefined ? obj[h] : '';
  });
  getSheet_(name).appendRow(row);
}

function nextId_(name) {
  const rows = getRows_(name);
  if (!rows.length) return 1;
  return Math.max.apply(null, rows.map(function (r) {
    return parseInt(r.id, 10) || 0;
  })) + 1;
}

function updateRowById_(name, id, updates) {
  const sheet = getSheet_(name);
  const headers = getHeaders_(name);
  const values = sheet.getDataRange().getValues();
  for (let i = 1; i < values.length; i++) {
    if (String(values[i][0]) === String(id)) {
      headers.forEach(function (h, col) {
        if (updates[h] !== undefined) {
          sheet.getRange(i + 1, col + 1).setValue(updates[h]);
        }
      });
      return;
    }
  }
}

function sumField_(name, field) {
  return getRows_(name).reduce(function (acc, r) {
    return acc + (parseFloat(r[field]) || 0);
  }, 0);
}

function inventario_() {
  return sumField_(SHEETS.CAMIONES, 'cantidad_cajas') - sumField_(SHEETS.SALIDAS, 'cantidad_cajas');
}

function resumenContable_(inicio, fin) {
  const filterDate = function (rows) {
    if (!inicio || !fin) return rows;
    return rows.filter(function (r) {
      return r.fecha >= inicio && r.fecha <= fin;
    });
  };
  const camiones = filterDate(getRows_(SHEETS.CAMIONES));
  const salidas = filterDate(getRows_(SHEETS.SALIDAS));
  const gastosRows = filterDate(getRows_(SHEETS.GASTOS));
  const pagos = getRows_(SHEETS.PAGOS);

  const compras = camiones.reduce(function (a, c) {
    return a + (parseFloat(c.cantidad_cajas) || 0) * (parseFloat(c.precio_compra_caja) || 0);
  }, 0);
  const ventas = salidas.reduce(function (a, s) {
    return a + (parseFloat(s.cantidad_cajas) || 0) * (parseFloat(s.precio_venta_caja) || 0);
  }, 0);
  const cajasVendidas = salidas.reduce(function (a, s) {
    return a + (parseFloat(s.cantidad_cajas) || 0);
  }, 0);
  const gastos = gastosRows.reduce(function (a, g) {
    return a + (parseFloat(g.monto) || 0);
  }, 0);
  const nominaPagada = pagos.filter(function (p) {
    return p.pagado === '1' || p.pagado === 1;
  }).reduce(function (a, p) {
    return a + (parseFloat(p.monto) || 0);
  }, 0);
  const nominaPendiente = pagos.filter(function (p) {
    return p.pagado !== '1' && p.pagado !== 1;
  }).reduce(function (a, p) {
    return a + (parseFloat(p.monto) || 0);
  }, 0);

  return {
    compras: compras,
    ventas: ventas,
    cajas_vendidas: cajasVendidas,
    gastos: gastos,
    nomina_pagada: nominaPagada,
    nomina_pendiente: nominaPendiente,
    ingresos: ventas,
    egresos: compras + gastos + nominaPagada,
    valor_neto: ventas - compras - gastos - nominaPagada,
    inventario: inventario_(),
  };
}

function today_() {
  return formatDate_(new Date());
}

function now_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
}

function formatDate_(d) {
  return Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}
