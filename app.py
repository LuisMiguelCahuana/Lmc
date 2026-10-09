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

SPREADSHEET_ID = "1IVNFi2DIUIRNW7jPMZ5zHA6anUtHkGeCJzN2UmooZTQ"

HOJAS_ITEMS = {
    "ITEM II": "ITEM_II",
    "ITEM III": "ITEM_III",
    "ITEM IV": "ITEM_IV",
}


# ============================================================
# ESTILOS ADAPTABLES A MODO CLARO Y OSCURO
# ============================================================

st.markdown("""
<style>
/* Utilizar los colores del tema seleccionado en Streamlit */
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

/* Indicadores */
[data-testid="stMetric"] {
    background-color: var(--secondary-background-color);
    border: 1px solid rgba(128, 128, 128, 0.30);
    padding: 14px;
    border-radius: 10px;
}

/* Campos de selección */
div[data-baseweb="select"] > div {
    background-color: var(--secondary-background-color);
}

/* Botones */
.stDownloadButton button {
    width: 100%;
    border-radius: 8px;
}

/* Tablas: conservar el estilo nativo para respetar ambos temas */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(128, 128, 128, 0.25);
    border-radius: 8px;
}

/* Mensajes y textos secundarios */
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
# NORMALIZAR PLACAS
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

    texto = str(valor).strip()

    return texto.lower() not in ("", "none", "nan", "nat")


# ============================================================
# CONVERTIR FECHAS
# ============================================================

def convertir_fecha(valor):
    """
    Convierte fechas de Google Sheets a pandas.Timestamp.
    Admite formatos como 05/10/2026 y 2026-10-05.
    """

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


# ============================================================
# LEER PLACAS MAESTRAS DE LOS COORDINADORES
# Placa: columna B de cada hoja ITEM
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_placas_maestras():
    cliente = conectar_google()
    archivo = cliente.open_by_key(SPREADSHEET_ID)

    resultado = {}

    for nombre_item, nombre_hoja in HOJAS_ITEMS.items():
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
# LEER HISTORIAL DE DISTRIBUCION
#
# A = FECHA
# B = PLACA
# C = HORA INICIO
# D = KM INICIAL
# E = HORA FIN
# F = KM FINAL
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_reportes():
    cliente = conectar_google()
    archivo = cliente.open_by_key(SPREADSHEET_ID)
    hoja = archivo.worksheet("Distribucion")

    # Leemos A:F para obtener la fecha y los kilómetros.
    filas = hoja.get("A2:F")

    registros = {}

    for fila in filas:
        fila = fila + [""] * (6 - len(fila))

        fecha = convertir_fecha(fila[0])  # Columna A
        placa = normalizar_placa(fila[1])  # Columna B
        km_inicial = fila[3]               # Columna D
        km_final = fila[5]                 # Columna F

        if not placa:
            continue

        if placa not in registros:
            registros[placa] = {
                "KM inicial registrado": False,
                "KM final registrado": False,
                "Registros encontrados": 0,
                "Fecha último reporte": pd.NaT,
                "Fecha último KM inicial": pd.NaT,
                "Fecha último KM final": pd.NaT,
            }

        datos = registros[placa]
        datos["Registros encontrados"] += 1

        # Fecha más reciente en que aparece la placa.
        if not pd.isna(fecha):
            fecha_actual = datos["Fecha último reporte"]

            if pd.isna(fecha_actual) or fecha > fecha_actual:
                datos["Fecha último reporte"] = fecha

        # KM inicial: conservar la fecha más reciente
        # de un registro que tenga KM inicial.
        if tiene_valor(km_inicial):
            datos["KM inicial registrado"] = True

            fecha_actual = datos["Fecha último KM inicial"]

            if not pd.isna(fecha):
                if pd.isna(fecha_actual) or fecha > fecha_actual:
                    datos["Fecha último KM inicial"] = fecha

        # KM final: conservar la fecha más reciente
        # de un registro que tenga KM final.
        if tiene_valor(km_final):
            datos["KM final registrado"] = True

            fecha_actual = datos["Fecha último KM final"]

            if not pd.isna(fecha):
                if pd.isna(fecha_actual) or fecha > fecha_actual:
                    datos["Fecha último KM final"] = fecha

    return registros


# ============================================================
# GENERAR COMPARACIÓN POR ÍTEM
# ============================================================

def generar_reporte(placas_maestras, registros):
    reportes = []

    for nombre_item, placas in placas_maestras.items():
        for placa in sorted(placas):
            datos = registros.get(placa, {})

            inicial = datos.get(
                "KM inicial registrado", False
            )
            final = datos.get(
                "KM final registrado", False
            )

            if inicial and final:
                estado = "COMPLETÓ KM INICIAL Y FINAL"
            elif inicial:
                estado = "SOLO KM INICIAL"
            elif final:
                estado = "SOLO KM FINAL"
            else:
                estado = "SIN REPORTE DE KM"

            fecha_ultimo = datos.get(
                "Fecha último reporte", pd.NaT
            )
            fecha_inicial = datos.get(
                "Fecha último KM inicial", pd.NaT
            )
            fecha_final = datos.get(
                "Fecha último KM final", pd.NaT
            )

            reportes.append({
                "Ítem": nombre_item,
                "Placa": placa,
                "Estado": estado,
                "KM inicial registrado": "Sí" if inicial else "No",
                "Fecha último KM inicial": mostrar_fecha(fecha_inicial),
                "KM final registrado": "Sí" if final else "No",
                "Fecha último KM final": mostrar_fecha(fecha_final),
                "Fecha último reporte": mostrar_fecha(fecha_ultimo),
                "Registros encontrados": datos.get(
                    "Registros encontrados", 0
                ),
            })

    return pd.DataFrame(reportes)


# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

st.title("🚙 CONTROL DE REPORTE DE KILOMETRAJE")

st.caption(
    "Comparación de las placas registradas por los coordinadores "
    "con el historial de la hoja Distribucion."
)

try:
    with st.spinner("Consultando Google Sheets..."):
        placas_maestras = cargar_placas_maestras()
        registros = cargar_reportes()
        df = generar_reporte(placas_maestras, registros)

except Exception as e:
    st.error(f"No se pudieron cargar los datos: {e}")
    st.stop()

if df.empty:
    st.warning("No se encontraron placas en las hojas de los ítems.")
    st.stop()


# ============================================================
# FILTROS
# ============================================================

col1, col2 = st.columns(2)

with col1:
    item_seleccionado = st.selectbox(
        "Seleccionar ítem",
        ["TODOS"] + list(HOJAS_ITEMS.keys()),
    )

with col2:
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

if item_seleccionado != "TODOS":
    filtrado = filtrado[
        filtrado["Ítem"] == item_seleccionado
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

sin_reporte = (
    filtrado["Estado"] == "SIN REPORTE DE KM"
).sum()

solo_inicial = (
    filtrado["Estado"] == "SOLO KM INICIAL"
).sum()

solo_final = (
    filtrado["Estado"] == "SOLO KM FINAL"
).sum()

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Placas maestras", total)
c2.metric("KM inicial y final", int(completos))
c3.metric("Solo KM inicial", int(solo_inicial))
c4.metric("Solo KM final", int(solo_final))
c5.metric("Sin reporte", int(sin_reporte))


# ============================================================
# RESUMEN POR ÍTEM
# ============================================================

st.subheader("Resumen por ítem")

resumen = (
    df.groupby(["Ítem", "Estado"])
    .size()
    .unstack(fill_value=0)
)

st.dataframe(
    resumen,
    use_container_width=True,
)


# ============================================================
# TABLA DETALLADA CON FECHAS
# ============================================================

st.subheader("Detalle de placas y fechas de reporte")

st.caption(
    "Las fechas corresponden al registro más reciente de cada tipo "
    "de kilometraje encontrado en el historial de Distribucion."
)

columnas_tabla = [
    "Ítem",
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
        ["Ítem", "Estado", "Placa"]
    ),
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# DESCARGAR REPORTE CSV
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
# ACTUALIZACIÓN MANUAL
# ============================================================

st.divider()

if st.button("🔄 ACTUALIZAR DATOS"):
    st.cache_data.clear()
    st.rerun()
