# El Maná – Gestión documental y contable de facturas
Aplicación de escritorio (Python, Tkinter y SQLite) para registrar facturas con sus
metadatos, adjuntar soportes (PDF, JPG, PNG), buscar, exportar un reporte CSV para la DIAN,
importar el Excel actual y hacer copias de seguridad.

## Requisitos
- Windows con Python 3 instalado
- Dependencias: `pip install -r requirements.txt`

## Ejecución
Doble clic en `start.bat` (o `El Mana.vbs`), o `python app.py`.
Al primer ingreso, usa el usuario administrador y cambia la contraseña inicial.

## Estructura
app.py (inicio) · el_mana.py (ventana y módulos de apoyo) · facturas.py (pestaña de facturas)
· database.py (base de datos y reglas)

Proyecto de grado – Ingeniería de Sistemas, UNAD. Autora: Virginia Rios Santis.

Corregir nombre de requirements.txt en README
