import streamlit as st
import gspread
import pandas as pd
import re

from datetime import datetime, date
from google.oauth2.service_account import Credentials


# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="Control de Reporte de Placas",
    page_icon="🚙",
    layout="wide",
)

# Archivo 1: distribución
SPREADSHEET_ID_DISTRIBUCION = (
    "1IVNFi2DIUIRNW7jPMZ5zHA6anUtHkGeCJzN2UmooZTQ"
)

# Archivo 2: control de pérdidas
SPREADSHEET_ID_PERDIDAS = (
    "1xhimNssLjBwgaT77gS0edeHA4QJntY-ueYcQs0UVBU0"
)

# Hojas maestras de cada archivo
HOJAS_DISTRIBUCION = {
    "ITEM II": "ITEM_II",
    "ITEM III": "ITEM_III",
    "ITEM IV": "ITEM_IV",
}

HOJAS_PERDIDAS = {
    "TingoMaria": "TingoMaria",
    "Huanuco": "Huanuco",
    "Pasco": "Pasco",
    "Facturacion": "Facturacion",
    "Sedapal": "Sedapal",
    "Hidrandina": "Hidrandina",
}


# ============================================================
# ESTILOS: MODO CLARO Y OSCURO
# ============================================================

st.markdown("""
<style>
.stApp {
    background-color: var(--background-color);
    color: var(--text-color);
}

h1, h2, h3, h4, p, label,
.stMarkdown, .stCaption,
[data-testid="stMetricLabel"],
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"] {
    color: var(--text-color);
}

[data-testid="stMetric"] {
    background-color: var(--secondary-background-color);
    border: 1px solid rgba(128, 128, 128, 0.30);
    padding: 14px;
    border-radius: 10px;
}

div[data-baseweb="select"] > div {
    background-color: var(--secondary-background-color);
}

.stDownloadButton button {
    width: 100%;
    border-radius: 8px;
}

[data-testid="stDataFrame"] {
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 8px;
}

[data-testid="stCaptionContainer"] {
    opacity: 0.85;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# CONEXIÓN A GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google():
    credenciales = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credenciales)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalizar_placa(valor):
    if valor is None:
        return ""

    valor = str(valor).strip().upper()
    valor = re.sub(r"[^A-Z0-9]", "", valor)

    if len(valor) != 6:
        return ""

    return valor[:3] + "-" + valor[3:]


def tiene_valor(valor):
    if valor is None:
        return False

    return str(valor).strip().lower() not in (
        "", "none", "nan", "nat"
    )


def convertir_fecha(valor):
    if not tiene_valor(valor):
        return pd.NaT

    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(valor).normalize()

    fecha = pd.to_datetime(
        str(valor).strip(),
        errors="coerce",
        dayfirst=True,
    )

    if pd.isna(fecha):
        return pd.NaT

    return pd.Timestamp(fecha).normalize()


def mostrar_fecha(valor):
    if pd.isna(valor):
        return "Sin fecha"

    return pd.Timestamp(valor).strftime("%d/%m/%Y")


def nuevo_registro():
    return {
        "KM inicial registrado": False,
        "KM final registrado": False,
        "Registros encontrados": 0,
        "Fecha último reporte": pd.NaT,
        "Fecha último KM inicial": pd.NaT,
        "Fecha último KM final": pd.NaT,
    }


def actualizar_fecha_mas_reciente(datos, campo, fecha):
    if pd.isna(fecha):
        return

    fecha_actual = datos[campo]

    if pd.isna(fecha_actual) or fecha > fecha_actual:
        datos[campo] = fecha


# ============================================================
# LEER PLACAS MAESTRAS DEL ARCHIVO DE DISTRIBUCIÓN
# Columna B: placa
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_placas_distribucion():
    cliente = conectar_google()
    archivo = cliente.open_by_key(
        SPREADSHEET_ID_DISTRIBUCION
    )

    resultado = {}

    for nombre_item, nombre_hoja in HOJAS_DISTRIBUCION.items():
        hoja = archivo.worksheet(nombre_hoja)
        filas = hoja.get("B2:B")

        placas = set()

        for fila in filas:
            valor = fila[0] if fila else ""
            placa = normalizar_placa(valor)

            if placa:
                placas.add(placa)

        resultado[nombre_item] = placas

    return resultado


# ============================================================
# LEER PLACAS MAESTRAS DEL ARCHIVO DE PÉRDIDAS
# Columna B: PLACA DE VEHÍCULO
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_placas_perdidas():
    cliente = conectar_google()
    archivo = cliente.open_by_key(
        SPREADSHEET_ID_PERDIDAS
    )

    resultado = {}

    for nombre_item, nombre_hoja in HOJAS_PERDIDAS.items():
        hoja = archivo.worksheet(nombre_hoja)
        filas = hoja.get("B2:B")

        placas = set()

        for fila in filas:
            valor = fila[0] if fila else ""
            placa = normalizar_placa(valor)

            if placa:
                placas.add(placa)

        resultado[nombre_item] = placas

    return resultado


# ============================================================
# PROCESAR HISTORIAL DE KILOMETRAJE
# ============================================================

def procesar_historial(filas, columna_placa,
                       columna_inicial, columna_final):
    registros = {}

    max_columna = max(
        columna_placa,
        columna_inicial,
        columna_final,
        0,
    )

    for fila in filas:
        fila = fila + [""] * (max_columna + 1 - len(fila))

        fecha = convertir_fecha(fila[0])
        placa = normalizar_placa(fila[columna_placa])
        km_inicial = fila[columna_inicial]
        km_final = fila[columna_final]

        if not placa:
            continue

        if placa not in registros:
            registros[placa] = nuevo_registro()

        datos = registros[placa]
        datos["Registros encontrados"] += 1

        actualizar_fecha_mas_reciente(
            datos, "Fecha último reporte", fecha
        )

        if tiene_valor(km_inicial):
            datos["KM inicial registrado"] = True

            actualizar_fecha_mas_reciente(
                datos, "Fecha último KM inicial", fecha
            )

        if tiene_valor(km_final):
            datos["KM final registrado"] = True

            actualizar_fecha_mas_reciente(
                datos, "Fecha último KM final", fecha
            )

    return registros


# ============================================================
# HISTORIAL DISTRIBUCION
# A = Fecha, B = Placa, D = KM inicial, F = KM final
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_reportes_distribucion():
    cliente = conectar_google()
    archivo = cliente.open_by_key(
        SPREADSHEET_ID_DISTRIBUCION
    )

    hoja = archivo.worksheet("Distribucion")
    filas = hoja.get("A2:F")

    # Dentro del rango A:F:
    # A = 0, B = 1, D = 3, F = 5
    return procesar_historial(
        filas,
        columna_placa=1,
        columna_inicial=3,
        columna_final=5,
    )


# ============================================================
# HISTORIAL CONTROLPERDIDAS
# A = Fecha, B = Placa, C = KM inicial, D = KM final
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_reportes_perdidas():
    cliente = conectar_google()
    archivo = cliente.open_by_key(
        SPREADSHEET_ID_PERDIDAS
    )

    hoja = archivo.worksheet("ControlPerdidas")
    filas = hoja.get("A2:D")

    # Dentro del rango A:D:
    # A = 0, B = 1, C = 2, D = 3
    return procesar_historial(
        filas,
        columna_placa=1,
        columna_inicial=2,
        columna_final=3,
    )


# ============================================================
# GENERAR REPORTE COMBINADO
# ============================================================

def generar_reporte(placas_distribucion,
                    placas_perdidas,
                    reportes_distribucion,
                    reportes_perdidas):

    filas_reporte = []

    fuentes = [
        (
            "Distribución",
            placas_distribucion,
            reportes_distribucion,
        ),
        (
            "Control de pérdidas",
            placas_perdidas,
            reportes_perdidas,
        ),
    ]

    for fuente, grupos_placas, registros in fuentes:
        for nombre_item, placas in grupos_placas.items():

            for placa in sorted(placas):
                datos = registros.get(placa, nuevo_registro())

                inicial = datos["KM inicial registrado"]
                final = datos["KM final registrado"]

                if inicial and final:
                    estado = "COMPLETÓ KM INICIAL Y FINAL"
                elif inicial:
                    estado = "SOLO KM INICIAL"
                elif final:
                    estado = "SOLO KM FINAL"
                else:
                    estado = "SIN REPORTE DE KM"

                filas_reporte.append({
                    "Fuente": fuente,
                    "Ítem / Unidad": nombre_item,
                    "Placa": placa,
                    "Estado": estado,
                    "KM inicial registrado": (
                        "Sí" if inicial else "No"
                    ),
                    "Fecha último KM inicial": mostrar_fecha(
                        datos["Fecha último KM inicial"]
                    ),
                    "KM final registrado": (
                        "Sí" if final else "No"
                    ),
                    "Fecha último KM final": mostrar_fecha(
                        datos["Fecha último KM final"]
                    ),
                    "Fecha último reporte": mostrar_fecha(
                        datos["Fecha último reporte"]
                    ),
                    "Registros encontrados": (
                        datos["Registros encontrados"]
                    ),
                })

    return pd.DataFrame(filas_reporte)


# ============================================================
# INTERFAZ
# ============================================================

st.title("🚙 CONTROL DE REPORTE DE KILOMETRAJE")

st.caption(
    "Control de placas, kilometraje inicial y final, y fechas "
    "de reporte de Distribución y Control de pérdidas."
)

try:
    with st.spinner("Consultando los dos archivos de Google Sheets..."):
        placas_distribucion = cargar_placas_distribucion()
        placas_perdidas = cargar_placas_perdidas()

        reportes_distribucion = cargar_reportes_distribucion()
        reportes_perdidas = cargar_reportes_perdidas()

        df = generar_reporte(
            placas_distribucion,
            placas_perdidas,
            reportes_distribucion,
            reportes_perdidas,
        )

except Exception as e:
    st.error(f"No se pudieron cargar los datos: {e}")
    st.info(
        "Verifica que la cuenta de servicio tenga acceso de lectura "
        "a ambos archivos y que existan todas las hojas indicadas."
    )
    st.stop()

if df.empty:
    st.warning("No se encontraron placas en las hojas maestras.")
    st.stop()


# ============================================================
# FILTROS
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:
    fuente_seleccionada = st.selectbox(
        "Fuente",
        [
            "TODAS",
            "Distribución",
            "Control de pérdidas",
        ],
    )

with col2:
    opciones_items = ["TODOS"] + sorted(
        df["Ítem / Unidad"].unique().tolist()
    )

    item_seleccionado = st.selectbox(
        "Ítem / Unidad",
        opciones_items,
    )

with col3:
    estado_seleccionado = st.selectbox(
        "Estado del reporte",
        [
            "TODOS",
            "COMPLETÓ KM INICIAL Y FINAL",
            "SOLO KM INICIAL",
            "SOLO KM FINAL",
            "SIN REPORTE DE KM",
        ],
    )

filtrado = df.copy()

if fuente_seleccionada != "TODAS":
    filtrado = filtrado[
        filtrado["Fuente"] == fuente_seleccionada
    ]

if item_seleccionado != "TODOS":
    filtrado = filtrado[
        filtrado["Ítem / Unidad"] == item_seleccionado
    ]

if estado_seleccionado != "TODOS":
    filtrado = filtrado[
        filtrado["Estado"] == estado_seleccionado
    ]


# ============================================================
# INDICADORES
# ============================================================

total = len(filtrado)

completos = (
    filtrado["Estado"] == "COMPLETÓ KM INICIAL Y FINAL"
).sum()

solo_inicial = (
    filtrado["Estado"] == "SOLO KM INICIAL"
).sum()

solo_final = (
    filtrado["Estado"] == "SOLO KM FINAL"
).sum()

sin_reporte = (
    filtrado["Estado"] == "SIN REPORTE DE KM"
).sum()

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Placas", total)
c2.metric("KM inicial y final", int(completos))
c3.metric("Solo KM inicial", int(solo_inicial))
c4.metric("Solo KM final", int(solo_final))
c5.metric("Sin reporte", int(sin_reporte))


# ============================================================
# RESUMEN POR FUENTE E ÍTEM
# ============================================================

st.subheader("Resumen por fuente e ítem")

resumen = (
    df.groupby(["Fuente", "Ítem / Unidad", "Estado"])
    .size()
    .unstack(fill_value=0)
)

st.dataframe(
    resumen,
    use_container_width=True,
)


# ============================================================
# TABLA DETALLADA
# ============================================================

st.subheader("Detalle de placas y fechas")

columnas_tabla = [
    "Fuente",
    "Ítem / Unidad",
    "Placa",
    "Estado",
    "KM inicial registrado",
    "Fecha último KM inicial",
    "KM final registrado",
    "Fecha último KM final",
    "Fecha último reporte",
    "Registros encontrados",
]

st.dataframe(
    filtrado[columnas_tabla].sort_values(
        ["Fuente", "Ítem / Unidad", "Estado", "Placa"]
    ),
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# DESCARGAR CSV
# ============================================================

salida = filtrado[columnas_tabla].to_csv(
    index=False,
    sep=";",
    encoding="utf-8-sig",
).encode("utf-8-sig")

st.download_button(
    "📥 DESCARGAR REPORTE CSV",
    data=salida,
    file_name="reporte_placas_kilometraje.csv",
    mime="text/csv",
    use_container_width=True,
)


# ============================================================
# ACTUALIZAR DATOS
# ============================================================

st.divider()

if st.button("🔄 ACTUALIZAR DATOS"):
    st.cache_data.clear()
    st.rerun()
