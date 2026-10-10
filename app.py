
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

# Archivo de Distribución
SPREADSHEET_ID_DISTRIBUCION = (
    "1IVNFi2DIUIRNW7jPMZ5zHA6anUtHkGeCJzN2UmooZTQ"
)

# Archivo de Control de pérdidas
SPREADSHEET_ID_PERDIDAS = (
    "1xhimNssLjBwgaT77gS0edeHA4QJntY-ueYcQs0UVBU0"
)

# Hojas maestras del archivo de Distribución
HOJAS_DISTRIBUCION = {
    "ITEM II": "ITEM_II",
    "ITEM III": "ITEM_III",
    "ITEM IV": "ITEM_IV",
}

# Hojas maestras del archivo de Control de pérdidas
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
# LEER PLACAS MAESTRAS
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_placas_maestras(spreadsheet_id, hojas):
    cliente = conectar_google()
    archivo = cliente.open_by_key(spreadsheet_id)

    resultado = {}

    for nombre, nombre_hoja in hojas.items():
        hoja = archivo.worksheet(nombre_hoja)
        filas = hoja.get("B2:B")

        placas = set()

        for fila in filas:
            valor = fila[0] if fila else ""
            placa = normalizar_placa(valor)

            if placa:
                placas.add(placa)

        resultado[nombre] = placas

    return resultado


# ============================================================
# PROCESAR HISTORIAL DE KILOMETRAJE
# ============================================================

def procesar_historial(
    filas,
    columna_placa,
    columna_inicial,
    columna_final,
):
    registros = {}

    max_columna = max(
        columna_placa,
        columna_inicial,
        columna_final,
        0,
    )

    for fila_original in filas:
        fila = list(fila_original)

        fila += [""] * max(
            0,
            max_columna + 1 - len(fila),
        )

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
            datos,
            "Fecha último reporte",
            fecha,
        )

        if tiene_valor(km_inicial):
            datos["KM inicial registrado"] = True

            actualizar_fecha_mas_reciente(
                datos,
                "Fecha último KM inicial",
                fecha,
            )

        if tiene_valor(km_final):
            datos["KM final registrado"] = True

            actualizar_fecha_mas_reciente(
                datos,
                "Fecha último KM final",
                fecha,
            )

    return registros


# ============================================================
# HISTORIAL DE DISTRIBUCION
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

    return procesar_historial(
        filas,
        columna_placa=1,
        columna_inicial=3,
        columna_final=5,
    )


# ============================================================
# HISTORIAL DE CONTROLPERDIDAS
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

    return procesar_historial(
        filas,
        columna_placa=1,
        columna_inicial=2,
        columna_final=3,
    )
# ============================================================
# CARGAR DETALLE DIARIO DE REPORTES
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_detalle_diario(spreadsheet_id, nombre_hoja, tipo):
    cliente = conectar_google()
    archivo = cliente.open_by_key(spreadsheet_id)
    hoja = archivo.worksheet(nombre_hoja)

    if tipo == "Distribución":
        filas = hoja.get("A2:F")
        columna_placa = 1
        columna_inicial = 3
        columna_final = 5
    else:
        filas = hoja.get("A2:D")
        columna_placa = 1
        columna_inicial = 2
        columna_final = 3

    registros = []

    for fila_original in filas:
        fila = list(fila_original)
        fila += [""] * max(0, 6 - len(fila))

        fecha = convertir_fecha(fila[0])
        placa = normalizar_placa(fila[columna_placa])

        if not placa or pd.isna(fecha):
            continue

        km_inicial = fila[columna_inicial]
        km_final = fila[columna_final]

        registros.append({
            "Fuente": tipo,
            "Fecha": fecha,
            "Placa": placa,
            "KM inicial": (
                "Sí" if tiene_valor(km_inicial) else "No"
            ),
            "KM final": (
                "Sí" if tiene_valor(km_final) else "No"
            ),
            "Estado diario": (
                "COMPLETO"
                if tiene_valor(km_inicial) and tiene_valor(km_final)
                else "SOLO KM INICIAL"
                if tiene_valor(km_inicial)
                else "SOLO KM FINAL"
                if tiene_valor(km_final)
                else "SIN KM"
            ),
        })

    return pd.DataFrame(registros)


def generar_reporte_diario(
    grupos_maestros,
    detalle,
    fuente,
    fecha_inicio,
    fecha_fin,
):
    filas = []

    # Obtener las placas que corresponden a la fuente elegida.
    placas_por_item = {}

    for nombre_item, placas in grupos_maestros.items():
        placas_por_item[nombre_item] = placas

    fechas = pd.date_range(
        start=fecha_inicio,
        end=fecha_fin,
        freq="D",
    )

    # Agrupar los registros por placa y fecha.
    if not detalle.empty:
        detalle_filtrado = detalle[
            (detalle["Fecha"] >= pd.Timestamp(fecha_inicio))
            & (detalle["Fecha"] <= pd.Timestamp(fecha_fin))
        ].copy()

        resumen_diario = (
            detalle_filtrado
            .groupby(["Placa", "Fecha"], as_index=False)
            .agg({
                "KM inicial": lambda x: (
                    "Sí" if (x == "Sí").any() else "No"
                ),
                "KM final": lambda x: (
                    "Sí" if (x == "Sí").any() else "No"
                ),
            })
        )
    else:
        resumen_diario = pd.DataFrame(
            columns=["Placa", "Fecha", "KM inicial", "KM final"]
        )

    # Crear una fila por cada placa y cada fecha del rango.
    for nombre_item, placas in placas_por_item.items():
        for placa in sorted(placas):
            for fecha in fechas:
                coincidencia = resumen_diario[
                    (resumen_diario["Placa"] == placa)
                    & (resumen_diario["Fecha"] == fecha)
                ]

                if coincidencia.empty:
                    km_inicial = "No"
                    km_final = "No"
                    estado = "SIN REPORTE"
                else:
                    registro = coincidencia.iloc[0]
                    km_inicial = registro["KM inicial"]
                    km_final = registro["KM final"]

                    if km_inicial == "Sí" and km_final == "Sí":
                        estado = "COMPLETO"
                    elif km_inicial == "Sí":
                        estado = "SOLO KM INICIAL"
                    elif km_final == "Sí":
                        estado = "SOLO KM FINAL"
                    else:
                        estado = "REPORTÓ SIN KM"

                filas.append({
                    "Fuente": fuente,
                    "Ítem / Unidad": nombre_item,
                    "Placa": placa,
                    "Fecha": fecha,
                    "Día": fecha.strftime("%A"),
                    "Reporte": (
                        "SÍ" if estado != "SIN REPORTE" else "NO"
                    ),
                    "KM inicial": km_inicial,
                    "KM final": km_final,
                    "Estado diario": estado,
                })

    return pd.DataFrame(filas)


# ============================================================
# GENERAR REPORTE DE KILOMETRAJE
# ============================================================

def generar_reporte_kilometraje(
    placas_distribucion,
    placas_perdidas,
    reportes_distribucion,
    reportes_perdidas,
):
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
                datos = registros.get(
                    placa,
                    nuevo_registro(),
                )

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
# GENERAR TABLA DE CRUCE DE PLACAS
# COMPARACIÓN EN AMBOS SENTIDOS
# ============================================================

def generar_tabla_cruce(
    placas_maestras,
    placas_reportadas,
    nombre_maestro,
    nombre_reporte,
):
    filas = []

    # Placas existentes en la hoja maestra
    for placa in sorted(placas_maestras):
        existe = placa in placas_reportadas

        filas.append({
            "Hoja maestra": nombre_maestro,
            "Placa": placa,
            "Cruce": "SÍ" if existe else "NO",
            "Detalle": (
                "Existe en ambas fuentes"
                if existe
                else f"No aparece en {nombre_reporte}"
            ),
        })

    # Placas del reporte que no existen en ninguna
    # de las hojas maestras de referencia
    for placa in sorted(
        placas_reportadas - placas_maestras
    ):
        filas.append({
            "Hoja maestra": nombre_maestro,
            "Placa": placa,
            "Cruce": "NO",
            "Detalle": (
                f"Está en {nombre_reporte}, "
                "pero no en las hojas maestras comparadas"
            ),
        })

    return pd.DataFrame(
        filas,
        columns=[
            "Hoja maestra",
            "Placa",
            "Cruce",
            "Detalle",
        ],
    )


# ============================================================
# GENERAR CRUCE AGRUPADO POR HOJA MAESTRA
# ============================================================

def generar_cruce_completo(
    grupos_maestros,
    placas_reportadas,
    nombre_reporte,
):
    tablas = []

    # Unión de todas las placas maestras.
    # Se utiliza para encontrar reportes sin correspondencia.
    todas_placas_maestras = set()

    for placas in grupos_maestros.values():
        todas_placas_maestras.update(placas)

    # Comparar cada hoja maestra por separado.
    for nombre_maestro, placas in grupos_maestros.items():
        tabla = generar_tabla_cruce(
            placas,
            placas_reportadas,
            nombre_maestro,
            nombre_reporte,
        )

        # Evitar repetir las placas que no están en ninguna
        # hoja maestra dentro de cada grupo.
        tabla = tabla[
            tabla["Detalle"] != (
                f"Está en {nombre_reporte}, "
                "pero no en las hojas maestras comparadas"
            )
        ]

        tablas.append(tabla)

    # Agregar una sola vez las placas que aparecen en el
    # historial, pero no en ninguna hoja maestra.
    placas_sin_maestro = (
        placas_reportadas - todas_placas_maestras
    )

    if placas_sin_maestro:
        inverso = pd.DataFrame([
            {
                "Hoja maestra": "NO FIGURA EN MAESTROS",
                "Placa": placa,
                "Cruce": "NO",
                "Detalle": (
                    f"Está en {nombre_reporte}, "
                    "pero no en ninguna hoja maestra"
                ),
            }
            for placa in sorted(placas_sin_maestro)
        ])

        tablas.append(inverso)

    if not tablas:
        return pd.DataFrame(
            columns=[
                "Hoja maestra",
                "Placa",
                "Cruce",
                "Detalle",
            ]
        )

    return pd.concat(
        tablas,
        ignore_index=True,
    )


# ============================================================
# COMPONENTE DE TABLA DE CRUCE
# ============================================================

def mostrar_tabla_cruce(df, nombre_archivo, clave):
    if df.empty:
        st.warning("No se encontraron placas para comparar.")
        return

    col1, col2 = st.columns([1, 2])

    with col1:
        filtro_hoja = st.selectbox(
            "Hoja maestra",
            ["TODAS"] + sorted(
                df["Hoja maestra"].unique().tolist()
            ),
            key=f"hoja_{clave}",
        )

    with col2:
        filtro_cruce = st.selectbox(
            "Resultado del cruce",
            ["TODOS", "SÍ", "NO"],
            key=f"cruce_{clave}",
        )

    vista = df.copy()

    if filtro_hoja != "TODAS":
        vista = vista[
            vista["Hoja maestra"] == filtro_hoja
        ]

    if filtro_cruce != "TODOS":
        vista = vista[
            vista["Cruce"] == filtro_cruce
        ]

    total = len(vista)
    con_cruce = int(
        (vista["Cruce"] == "SÍ").sum()
    )
    sin_cruce = int(
        (vista["Cruce"] == "NO").sum()
    )

    c1, c2, c3 = st.columns(3)

    c1.metric("Placas evaluadas", total)
    c2.metric("Con cruce", con_cruce)
    c3.metric("Sin cruce", sin_cruce)

    st.dataframe(
        vista.sort_values(
            ["Hoja maestra", "Cruce", "Placa"]
        ),
        use_container_width=True,
        hide_index=True,
    )

    salida = vista.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig",
    ).encode("utf-8-sig")

    st.download_button(
        "📥 DESCARGAR CRUCE CSV",
        data=salida,
        file_name=nombre_archivo,
        mime="text/csv",
        use_container_width=True,
        key=f"descarga_{clave}",
    )


# ============================================================
# CARGA DE DATOS
# ============================================================

st.title("🚙 CONTROL DE REPORTE DE KILOMETRAJE")

st.caption(
    "Consulta de kilometraje y comparación de placas "
    "entre las hojas maestras y los historiales."
)

try:
    with st.spinner("Consultando los archivos de Google Sheets..."):

        # Hojas maestras
        placas_distribucion = cargar_placas_maestras(
            SPREADSHEET_ID_DISTRIBUCION,
            HOJAS_DISTRIBUCION,
        )

        placas_perdidas = cargar_placas_maestras(
            SPREADSHEET_ID_PERDIDAS,
            HOJAS_PERDIDAS,
        )

        # Historiales de kilometraje
        reportes_distribucion = cargar_reportes_distribucion()
        reportes_perdidas = cargar_reportes_perdidas()
        # Historial detallado para el reporte diario
        detalle_distribucion = cargar_detalle_diario(
            SPREADSHEET_ID_DISTRIBUCION,
            "Distribucion",
            "Distribución",
        )

        detalle_perdidas = cargar_detalle_diario(
            SPREADSHEET_ID_PERDIDAS,
            "ControlPerdidas",
            "Control de pérdidas",
        )


        # Reporte de kilometraje original
        df = generar_reporte_kilometraje(
            placas_distribucion,
            placas_perdidas,
            reportes_distribucion,
            reportes_perdidas,
        )

        # Cruces independientes
        df_cruce_items = generar_cruce_completo(
            placas_distribucion,
            set(reportes_perdidas.keys()),
            "ControlPerdidas",
        )

        df_cruce_unidades = generar_cruce_completo(
            placas_perdidas,
            set(reportes_distribucion.keys()),
            "Distribucion",
        )

except Exception as e:
    st.error(f"No se pudieron cargar los datos: {e}")

    st.info(
        "Verifica que la cuenta de servicio tenga acceso de lectura "
        "a ambos archivos y que existan todas las hojas indicadas."
    )

    st.stop()


# ============================================================
# PESTAÑAS PRINCIPALES
# ============================================================

tab_km, tab_items, tab_unidades, tab_diario = st.tabs([
    "📊 Reporte de kilometraje",
    "🔎 Ítems vs ControlPerdidas",
    "🚙 Unidades vs Distribucion",
    "📅 Reporte diario de placas",
])


# ============================================================
# PESTAÑA 1: REPORTE DE KILOMETRAJE
# ============================================================

with tab_km:

    if df.empty:
        st.warning(
            "No se encontraron placas en las hojas maestras."
        )
    else:

        st.subheader("Control de kilometraje")

        col1, col2, col3 = st.columns(3)

        with col1:
            fuente_seleccionada = st.selectbox(
                "Fuente",
                [
                    "TODAS",
                    "Distribución",
                    "Control de pérdidas",
                ],
                key="km_fuente",
            )

        with col2:
            opciones_items = ["TODOS"] + sorted(
                df["Ítem / Unidad"].unique().tolist()
            )

            item_seleccionado = st.selectbox(
                "Ítem / Unidad",
                opciones_items,
                key="km_item",
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
                key="km_estado",
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

        completos = int(
            (
                filtrado["Estado"]
                == "COMPLETÓ KM INICIAL Y FINAL"
            ).sum()
        )

        solo_inicial = int(
            (filtrado["Estado"] == "SOLO KM INICIAL").sum()
        )

        solo_final = int(
            (filtrado["Estado"] == "SOLO KM FINAL").sum()
        )

        sin_reporte = int(
            (filtrado["Estado"] == "SIN REPORTE DE KM").sum()
        )

        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("Placas", len(filtrado))
        c2.metric("KM inicial y final", completos)
        c3.metric("Solo KM inicial", solo_inicial)
        c4.metric("Solo KM final", solo_final)
        c5.metric("Sin reporte", sin_reporte)

        st.subheader("Resumen por fuente e ítem")

        resumen = (
            df.groupby(
                ["Fuente", "Ítem / Unidad", "Estado"]
            )
            .size()
            .unstack(fill_value=0)
        )

        st.dataframe(
            resumen,
            use_container_width=True,
        )

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

        salida_km = filtrado[columnas_tabla].to_csv(
            index=False,
            sep=";",
            encoding="utf-8-sig",
        ).encode("utf-8-sig")

        st.download_button(
            "📥 DESCARGAR REPORTE DE KILOMETRAJE",
            data=salida_km,
            file_name="reporte_placas_kilometraje.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ============================================================
# PESTAÑA 2: CRUCE DE ÍTEMS CON CONTROLPERDIDAS
# ============================================================

with tab_items:

    st.subheader(
        "Cruce de ITEM_II, ITEM_III e ITEM_IV con ControlPerdidas"
    )

    st.caption(
        "Compara las placas maestras de los tres ítems con las "
        "placas registradas en el historial ControlPerdidas. "
        "El resultado inverso identifica placas que reportan "
        "sin figurar en ninguna de las tres hojas maestras."
    )

    mostrar_tabla_cruce(
        df_cruce_items,
        "cruce_items_control_perdidas.csv",
        "items",
    )


# ============================================================
# PESTAÑA 3: CRUCE DE UNIDADES CON DISTRIBUCION
# ============================================================

with tab_unidades:

    st.subheader(
        "Cruce de unidades maestras con Distribucion"
    )

    st.caption(
        "Compara TingoMaria, Huanuco, Pasco, Facturacion, "
        "Sedapal e Hidrandina con el historial Distribucion. "
        "El resultado inverso identifica placas de Distribucion "
        "que no figuran en ninguna de las seis hojas maestras."
    )

    mostrar_tabla_cruce(
        df_cruce_unidades,
        "cruce_unidades_distribucion.csv",
        "unidades",
    )
# ============================================================
# PESTAÑA 4: REPORTE DIARIO DE PLACAS
# ============================================================

with tab_diario:

    st.subheader("📅 Reporte diario de placas")
    st.caption(
        "Consulta qué fechas registró cada placa y cuáles "
        "no presentan registros en el historial."
    )

    c1, c2 = st.columns(2)

    with c1:
        fuente_diaria = st.selectbox(
            "Fuente del reporte",
            ["Distribución", "Control de pérdidas"],
            key="diario_fuente",
        )

    with c2:
        estado_diario = st.selectbox(
            "Estado diario",
            [
                "TODOS",
                "REPORTÓ",
                "SIN REPORTE",
                "COMPLETO",
                "SOLO KM INICIAL",
                "SOLO KM FINAL",
                "REPORTÓ SIN KM",
            ],
            key="diario_estado",
        )

    # Elegir las placas maestras y el historial según la fuente.
    if fuente_diaria == "Distribución":
        grupos_diarios = placas_distribucion
        detalle_diario = detalle_distribucion
    else:
        grupos_diarios = placas_perdidas
        detalle_diario = detalle_perdidas

    fechas_disponibles = []

    if not detalle_diario.empty:
        fechas_disponibles = (
            detalle_diario["Fecha"].dropna().tolist()
        )

    fecha_actual = date.today()

    if fechas_disponibles:
        fecha_minima = min(fechas_disponibles).date()
        fecha_maxima = max(fechas_disponibles).date()
    else:
        fecha_minima = fecha_actual
        fecha_maxima = fecha_actual

    c1, c2 = st.columns(2)

    with c1:
        fecha_inicio = st.date_input(
            "Fecha inicial",
            value=fecha_minima,
            key="diario_fecha_inicio",
        )

    with c2:
        fecha_fin = st.date_input(
            "Fecha final",
            value=fecha_maxima,
            key="diario_fecha_fin",
        )

    if fecha_inicio > fecha_fin:
        st.error(
            "La fecha inicial no puede ser posterior a la fecha final."
        )
        st.stop()

    # Generar la matriz de placa por día.
    df_diario = generar_reporte_diario(
        grupos_maestros=grupos_diarios,
        detalle=detalle_diario,
        fuente=fuente_diaria,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )

    if df_diario.empty:
        st.warning(
            "No se encontraron placas maestras para esta fuente."
        )
    else:

        # Filtros adicionales.
        c1, c2 = st.columns(2)

        with c1:
            item_diario = st.selectbox(
                "Ítem / Unidad",
                ["TODOS"] + sorted(
                    df_diario["Ítem / Unidad"].unique().tolist()
                ),
                key="diario_item",
            )

        with c2:
            placa_diaria = st.selectbox(
                "Placa",
                ["TODAS"] + sorted(
                    df_diario["Placa"].unique().tolist()
                ),
                key="diario_placa",
            )

        vista_diaria = df_diario.copy()

        if item_diario != "TODOS":
            vista_diaria = vista_diaria[
                vista_diaria["Ítem / Unidad"] == item_diario
            ]

        if placa_diaria != "TODAS":
            vista_diaria = vista_diaria[
                vista_diaria["Placa"] == placa_diaria
            ]

        if estado_diario == "REPORTÓ":
            vista_diaria = vista_diaria[
                vista_diaria["Reporte"] == "SÍ"
            ]
        elif estado_diario == "SIN REPORTE":
            vista_diaria = vista_diaria[
                vista_diaria["Reporte"] == "NO"
            ]
        elif estado_diario != "TODOS":
            vista_diaria = vista_diaria[
                vista_diaria["Estado diario"] == estado_diario
            ]

        # Indicadores.
        total_dias = len(vista_diaria)
        dias_reportados = int(
            (vista_diaria["Reporte"] == "SÍ").sum()
        )
        dias_sin_reporte = int(
            (vista_diaria["Reporte"] == "NO").sum()
        )
        porcentaje = (
            dias_reportados / total_dias * 100
            if total_dias else 0
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Placa-días evaluados", total_dias)
        c2.metric("Días con reporte", dias_reportados)
        c3.metric("Días sin reporte", dias_sin_reporte)
        c4.metric("Cumplimiento", f"{porcentaje:.1f}%")

        st.subheader("Detalle por fecha y placa")

        vista_mostrar = vista_diaria.copy()
        vista_mostrar["Fecha"] = vista_mostrar["Fecha"].dt.strftime(
            "%d/%m/%Y"
        )

        st.dataframe(
            vista_mostrar.sort_values(
                ["Ítem / Unidad", "Placa", "Fecha"]
            ),
            use_container_width=True,
            hide_index=True,
        )

        csv_diario = vista_mostrar.to_csv(
            index=False,
            sep=";",
            encoding="utf-8-sig",
        ).encode("utf-8-sig")

        st.download_button(
            "📥 DESCARGAR REPORTE DIARIO CSV",
            data=csv_diario,
            file_name="reporte_diario_placas.csv",
            mime="text/csv",
            use_container_width=True,
            key="descargar_diario_placas",
        )

        # Tabla adicional: resumen por placa.
        st.subheader("Resumen de cumplimiento por placa")

        if not vista_diaria.empty:
            resumen_placas = (
                vista_diaria.groupby(
                    ["Fuente", "Ítem / Unidad", "Placa"],
                    as_index=False,
                )
                .agg(
                    **{
                        "Días evaluados": ("Fecha", "count"),
                        "Días con reporte": (
                            "Reporte",
                            lambda x: (x == "SÍ").sum(),
                        ),
                        "Días sin reporte": (
                            "Reporte",
                            lambda x: (x == "NO").sum(),
                        ),
                    }
                )
            )

            resumen_placas["Cumplimiento (%)"] = (
                resumen_placas["Días con reporte"]
                / resumen_placas["Días evaluados"]
                * 100
            ).round(1)

            st.dataframe(
                resumen_placas,
                use_container_width=True,
                hide_index=True,
            )

            csv_resumen = resumen_placas.to_csv(
                index=False,
                sep=";",
                encoding="utf-8-sig",
            ).encode("utf-8-sig")

            st.download_button(
                "📥 DESCARGAR RESUMEN POR PLACA",
                data=csv_resumen,
                file_name="resumen_cumplimiento_placas.csv",
                mime="text/csv",
                use_container_width=True,
                key="descargar_resumen_placas",
            )


# ============================================================
# ACTUALIZAR DATOS
# ============================================================

st.divider()

if st.button(
    "🔄 ACTUALIZAR DATOS",
    use_container_width=True,
):
    st.cache_data.clear()
    st.rerun()
