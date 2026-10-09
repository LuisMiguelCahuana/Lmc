
import streamlit as st
import gspread
import pandas as pd
import re

from google.oauth2.service_account import Credentials


# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="Control de Reporte de Placas",
    page_icon="🚙",
    layout="wide",
)

SPREADSHEET_ID = (
    "1IVNFi2DIUIRNW7jPMZ5zHA6anUtHkGeCJzN2UmooZTQ"
)

HOJAS_ITEMS = {
    "ITEM II": "ITEM_II",
    "ITEM III": "ITEM_III",
    "ITEM IV": "ITEM_IV",
}


# ============================================================
# ESTILOS
# ============================================================

st.markdown("""
<style>
.stApp {
    background: #f5f7fb;
}
h1, h2, h3 {
    color: #12345a;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# CONEXIÓN
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
    valor = str(valor or "").strip().upper()
    valor = re.sub(r"[^A-Z0-9]", "", valor)

    if len(valor) != 6:
        return ""

    return valor[:3] + "-" + valor[3:]


def tiene_valor(valor):
    return str(valor or "").strip() not in ("", "None", "nan")


# ============================================================
# LEER PLACAS ACTUALIZADAS POR LOS COORDINADORES
# PLACA = COLUMNA B
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
# LEER REPORTES DE KILOMETRAJE
#
# B = PLACA
# D = KM INICIAL
# F = KM FINAL
#
# Se consideran los registros de toda la hoja.
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_reportes():
    cliente = conectar_google()
    archivo = cliente.open_by_key(SPREADSHEET_ID)
    hoja = archivo.worksheet("Distribucion")

    filas = hoja.get("B2:F")

    registros = {}

    for fila in filas:
        fila = fila + [""] * (5 - len(fila))

        placa = normalizar_placa(fila[0])
        km_inicial = fila[2]  # Columna D
        km_final = fila[4]    # Columna F

        if not placa:
            continue

        if placa not in registros:
            registros[placa] = {
                "KM inicial registrado": False,
                "KM final registrado": False,
                "Registros encontrados": 0,
            }

        registros[placa]["Registros encontrados"] += 1

        if tiene_valor(km_inicial):
            registros[placa]["KM inicial registrado"] = True

        if tiene_valor(km_final):
            registros[placa]["KM final registrado"] = True

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

            reportes.append({
                "Ítem": nombre_item,
                "Placa": placa,
                "Estado": estado,
                "KM inicial registrado": "Sí" if inicial else "No",
                "KM final registrado": "Sí" if final else "No",
                "Registros encontrados": datos.get(
                    "Registros encontrados", 0
                ),
            })

    return pd.DataFrame(reportes)


# ============================================================
# INTERFAZ
# ============================================================

st.title("🚙 CONTROL DE REPORTE DE KILOMETRAJE")
st.caption(
    "Comparación de placas actualizadas por los coordinadores "
    "frente a los registros de la hoja Distribucion."
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

c1, c2, c3, c4 = st.columns(4)

c1.metric("Placas maestras", total)
c2.metric("KM inicial y final", int(completos))
c3.metric("Solo KM inicial", int(solo_inicial))
c4.metric("Sin reporte", int(sin_reporte))


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
# TABLA DETALLADA
# ============================================================

st.subheader("Detalle de placas")

st.dataframe(
    filtrado.sort_values(["Ítem", "Estado", "Placa"]),
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# DESCARGAR EXCEL
# ============================================================

salida = filtrado.to_csv(
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
