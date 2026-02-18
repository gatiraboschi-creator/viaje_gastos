import streamlit as st
import pandas as pd
import gspread
import uuid


from datetime import date
from google.oauth2.service_account import Credentials
from datetime import datetime 

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import fonts
from reportlab.lib.styles import getSampleStyleSheet
import os

st.set_page_config(
    page_title="Gastos de Viaje",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* Quita padding extra */
.block-container { padding-top: 1rem; padding-bottom: 1rem; }

/* Botones grandes */
.stButton > button {
  width: 100%;
  padding: 0.75rem 1rem;
  border-radius: 14px;
  font-weight: 600;
}

/* Inputs más cómodos */
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {
  border-radius: 12px !important;
}

/* Cards */
.card {
  background: #ffffff10;
  border: 1px solid #ffffff20;
  border-radius: 16px;
  padding: 12px 14px;
  margin: 10px 0;
}

/* Tabla: evita que se “desborde” feo en móvil */
div[data-testid="stDataFrame"] { overflow-x: auto; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_ws():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )

    gc = gspread.authorize(creds)

    sh = gc.open_by_key(st.secrets["sheets"]["spreadsheet_id"])
    ws = sh.worksheet(st.secrets["sheets"]["worksheet"])

    return ws


import re

def load_gastos_from_sheet(personas):
    ws = get_ws()
    values = ws.get_all_values()
    if len(values) < 2:
        return pd.DataFrame()

    headers = [h.strip() for h in values[0]]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

    # columnas numéricas
    numeric_cols = ["monto", "cambio_a_base", "monto_base"] + personas

    def to_num(x):
        if x is None:
            return 0.0
        s = str(x).strip()
        if s == "":
            return 0.0

        # deja solo dígitos, coma, punto y signo
        s = re.sub(r"[^0-9,.\-]", "", s)

        # Tu caso: 333,3333333  -> 333.3333333
        # y 1000 -> 1000
        # y 1.234,56 -> 1234.56
        if "," in s and "." in s:
            # si tiene ambos, asumimos formato AR: 1.234,56
            s = s.replace(".", "")
            s = s.replace(",", ".")
        elif "," in s and "." not in s:
            # solo coma: decimal
            s = s.replace(",", ".")

        try:
            return float(s)
        except:
            return 0.0

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(to_num)
        else:
            df[col] = 0.0

    return df



def append_gasto_to_sheet(row, personas):
    ws = get_ws()
    headers = ws.row_values(1)

    # Asegurar que existan las columnas esperadas
    needed = ["id", "fecha", "concepto", "pago", "monto", "moneda", "cambio_a_base", "monto_base"] + personas
    missing = [c for c in needed if c not in headers]
    if missing:
        raise ValueError(f"Faltan columnas en la Sheet (fila 1): {missing}")

    # Evitar duplicados por id
    id_idx = headers.index("id")
    values = ws.get_all_values()
    if len(values) > 1:
        existing_ids = {r[id_idx] for r in values[1:] if len(r) > id_idx and r[id_idx]}
        if row["id"] in existing_ids:
            return

    # Armar fila en el mismo orden que los headers de la hoja
    ordered = [row.get(h, "") for h in headers]
    ws.append_row(ordered, value_input_option="USER_ENTERED")




st.set_page_config(page_title="Gastos de Viaje", layout="wide")

# -------------------------
# CSS (estilo claro)
# -------------------------
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1200px;}
      h1, h2, h3 {letter-spacing: -0.5px;}
      .card {
        background: #ffffff;
        border: 1px solid #eef0f3;
        border-radius: 18px;
        padding: 18px 18px;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
      }
      .hero {
        background: linear-gradient(135deg, #ffffff 0%, #f6f8ff 40%, #f3f8ff 100%);
        border: 1px solid #eef0f3;
        border-radius: 22px;
        padding: 28px 26px;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
      }
      .muted {color:#6b7280; font-size: 0.98rem;}
      .pill {
        display:inline-block;
        background:#f3f4f6;
        border:1px solid #e5e7eb;
        color:#111827;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        margin-right: 8px;
      }
      .small {font-size: 0.9rem; color:#6b7280;}
      div[data-testid="stMetricValue"] {font-size: 1.35rem;}
      section[data-testid="stSidebar"] {background: #fbfbfd;}
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------
# Estado
# -------------------------
def init_state():
    if "personas" not in st.session_state:
        st.session_state.personas = ["Quique", "Rafa", "Gus"]
    if "gastos" not in st.session_state:
        st.session_state.gastos = []
    if "base_moneda" not in st.session_state:
        st.session_state.base_moneda = "ARS"
    if "pagina" not in st.session_state:
        st.session_state.pagina = "inicio"  # inicio visual

init_state()

# -------------------------
# Helpers
# -------------------------
def normalize_currency(monto: float, cambio_a_base: float) -> float:
    return float(monto) * float(cambio_a_base)

def compute_balances(df: pd.DataFrame, personas: list[str]) -> pd.Series:
    if df is None or df.empty:
        return pd.Series({p: 0.0 for p in personas})

    # Asegurar columnas necesarias
    for col in ["pago", "monto_base"]:
        if col not in df.columns:
            raise ValueError(f"Falta la columna '{col}' en la Sheet.")

    for p in personas:
        if p not in df.columns:
            df[p] = 0.0

    # Pagos (quién pagó cuánto total)
    pagos = df.groupby("pago")["monto_base"].sum()

    # Consumos (cuánto le corresponde a cada persona)
    consumos = {p: float(df[p].sum()) for p in personas}

    balance = {}
    for p in personas:
        balance[p] = float(pagos.get(p, 0.0)) - float(consumos.get(p, 0.0))

    return pd.Series(balance).sort_values(ascending=False)
    st.write("DEBUG pagos por persona:", df.groupby("pago")["monto_base"].sum().to_dict())
    st.write("DEBUG consumos por persona:", {p: float(df[p].sum()) for p in personas})
    st.write("DEBUG balance:", balance.to_dict() if hasattr(balance, "to_dict") else dict(balance))



def settle_up(balance: pd.Series, eps=1e-6) -> pd.DataFrame:
    creditors = []
    debtors = []
    for person, amt in balance.items():
        if amt > eps:
            creditors.append([person, amt])
        elif amt < -eps:
            debtors.append([person, -amt])

    transfers = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d_name, d_amt = debtors[i]
        c_name, c_amt = creditors[j]
        x = min(d_amt, c_amt)
        if x > eps:
            transfers.append({"De": d_name, "Para": c_name, "Monto": round(x, 2)})
        debtors[i][1] -= x
        creditors[j][1] -= x
        if debtors[i][1] <= eps:
            i += 1
        if creditors[j][1] <= eps:
            j += 1

    return pd.DataFrame(transfers)

def money(v: float, symbol: str) -> str:
    s = f"{symbol}{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.markdown("## ⚙️ Configuración")

    personas_txt = st.text_area(
        "Personas (una por línea)",
        "\n".join(st.session_state.personas),
        height=110
    )
    personas = [p.strip() for p in personas_txt.splitlines() if p.strip()]
    if len(personas) >= 2:
        st.session_state.personas = personas
    personas = st.session_state.personas

    st.session_state.base_moneda = st.selectbox("Moneda base", ["ARS", "USD", "EUR"],
                                                index=["ARS", "USD", "EUR"].index(st.session_state.base_moneda))
    base = st.session_state.base_moneda
    simbolo = {"ARS": "$", "USD": "US$", "EUR": "€"}[base]

    st.markdown("---")
    if st.button("🏠 Volver a inicio", use_container_width=True):
        st.session_state.pagina = "inicio"
        st.rerun()

 

def generar_pdf(df, balance, base_moneda):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase import pdfmetrics

    file_path = "resumen_viaje.pdf"
    doc = SimpleDocTemplate(file_path)

    elements = []

    # Fuente compatible UTF-8
    pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))

    style = ParagraphStyle(
        name='Normal',
        fontName='HYSMyeongJo-Medium',
        fontSize=12,
    )

    elements.append(Paragraph("Resumen de Gastos de Viaje", style))
    elements.append(Spacer(1, 0.3 * inch))

    # Tabla gastos
    data = [["Fecha", "Concepto", "Pagó", "Monto Base"]]
    for _, row in df.iterrows():
        data.append([
            row["fecha"],
            row["concepto"],
            row["pago"],
            f"{row['monto_base']:.2f} {base_moneda}"
        ])

    table = Table(data)
    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))

    # Tabla balances
    data_balance = [["Persona", "Balance"]]
    for persona, valor in balance.items():
        data_balance.append([persona, f"{valor:.2f} {base_moneda}"])

    table2 = Table(data_balance)
    elements.append(table2)

    doc.build(elements)

    return file_path

from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
import tempfile
import pandas as pd

def generar_pdf_ejecutivo(df: pd.DataFrame, personas: list[str], simbolo="$", titulo="Viaje NYC – Amsterdam 2026"):
    styles = getSampleStyleSheet()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    file_path = tmp.name
    tmp.close()

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=1.2*cm,
        leftMargin=1.2*cm,
        topMargin=1.2*cm,
        bottomMargin=1.2*cm
    )

    def fmt_money(x):
        try:
            return f"{simbolo}{float(x):,.2f}"
        except:
            return f"{simbolo}0.00"

    elements = []

    # ===== ENCABEZADO EJECUTIVO (SIN PORTADA) =====
    elements.append(Paragraph(f"{titulo} — Informe Ejecutivo", styles["Title"]))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"Participantes: {', '.join(personas)}", styles["Normal"]))
    elements.append(Paragraph(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # ===== RESUMEN =====
    elements.append(Paragraph("Resumen", styles["Heading1"]))
    elements.append(Spacer(1, 6))

    total_base = float(pd.to_numeric(df.get("monto_base", 0), errors="coerce").fillna(0.0).sum())
    por_persona = total_base / len(personas) if personas else 0.0

    resumen_tbl = Table([
        ["Total (base)", fmt_money(total_base)],
        ["Por persona (base)", fmt_money(por_persona)],
        ["Cantidad de gastos", str(len(df))]
    ], colWidths=[7*cm, 7*cm])
    resumen_tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    elements.append(resumen_tbl)
    elements.append(Spacer(1, 14))

    # ===== PAGÓ / CONSUMIÓ / BALANCE =====
    elements.append(Paragraph("Pagó, consumió y balance", styles["Heading2"]))
    elements.append(Spacer(1, 6))

    if "pago" in df.columns and "monto_base" in df.columns:
        pagos = df.groupby("pago")["monto_base"].sum()
    else:
        pagos = pd.Series(dtype=float)

    consumos = {p: float(pd.to_numeric(df.get(p, 0), errors="coerce").fillna(0.0).sum()) for p in personas}
    balance = {p: float(pagos.get(p, 0.0)) - float(consumos.get(p, 0.0)) for p in personas}

    pcb_rows = [["Persona", "Pagó", "Consumió", "Balance"]]
    for p in personas:
        pcb_rows.append([p, fmt_money(pagos.get(p, 0.0)), fmt_money(consumos.get(p, 0.0)), fmt_money(balance.get(p, 0.0))])

    pcb_tbl = Table(pcb_rows, repeatRows=1, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    pcb_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ("PADDING", (0,0), (-1,-1), 4),
    ]))
    elements.append(pcb_tbl)
    elements.append(Spacer(1, 14))

    # ===== TRANSFERENCIAS =====
    elements.append(Paragraph("Quién le transfiere a quién", styles["Heading2"]))
    elements.append(Spacer(1, 6))

    try:
        balance_series = pd.Series(balance).sort_values(ascending=False)
        tx = settle_up(balance_series)  # debe devolver DataFrame
    except Exception:
        tx = pd.DataFrame()

    if tx is None or tx.empty:
        elements.append(Paragraph("No hay transferencias pendientes.", styles["Normal"]))
    else:
        tx_show = tx.copy()
        if "Monto" in tx_show.columns:
            tx_show["Monto"] = tx_show["Monto"].apply(fmt_money)

        tx_rows = [list(tx_show.columns)] + tx_show.astype(str).values.tolist()
        tx_tbl = Table(tx_rows, repeatRows=1)
        tx_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 9),
            ("FONTSIZE", (0,1), (-1,-1), 9),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
            ("PADDING", (0,0), (-1,-1), 4),
        ]))
        elements.append(tx_tbl)

    # ===== DETALLE (nueva página) =====
    elements.append(PageBreak())
    elements.append(Paragraph("Detalle de gastos", styles["Heading1"]))
    elements.append(Spacer(1, 8))

    cols = ["fecha", "concepto", "pago", "monto", "moneda", "cambio_a_base", "monto_base"] + personas
    cols = [c for c in cols if c in df.columns]

    detalle = df[cols].copy()
    for c in ["monto", "cambio_a_base", "monto_base"] + [p for p in personas if p in detalle.columns]:
        detalle[c] = pd.to_numeric(detalle[c], errors="coerce").fillna(0.0).round(2)

    data = [cols] + detalle.astype(str).values.tolist()

    det_tbl = Table(data, repeatRows=1)
    det_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 8),
        ("FONTSIZE", (0,1), (-1,-1), 7),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ("PADDING", (0,0), (-1,-1), 3),
    ]))
    elements.append(det_tbl)

    doc.build(elements)
    return file_path


def generar_pdf_gastos(df: pd.DataFrame, personas: list[str], titulo="📋 Gastos cargados"):
    styles = getSampleStyleSheet()

    # Archivo temporal
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    file_path = tmp.name
    tmp.close()

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=1.2*cm,
        leftMargin=1.2*cm,
        topMargin=1.2*cm,
        bottomMargin=1.2*cm
    )

    elements = []
    elements.append(Paragraph(titulo, styles["Title"]))
    elements.append(Spacer(1, 10))

    # Columnas a mostrar
    cols = ["fecha", "concepto", "pago", "monto", "moneda", "cambio_a_base", "monto_base"] + personas
    cols = [c for c in cols if c in df.columns]

    show = df[cols].copy()

    # Redondeos
    for c in ["monto", "cambio_a_base", "monto_base"] + [p for p in personas if p in show.columns]:
        if c in show.columns:
            show[c] = pd.to_numeric(show[c], errors="coerce").fillna(0.0).round(2)

    # Convertir a strings (para PDF)
    data = [cols] + show.astype(str).values.tolist()

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 10))

    # Totales (opcional)
    if "monto_base" in df.columns:
        total_base = float(pd.to_numeric(df["monto_base"], errors="coerce").fillna(0.0).sum())
        elements.append(Paragraph(f"<b>Total (base):</b> {total_base:,.2f}", styles["Normal"]))

    doc.build(elements)
    return file_path


# -------------------------
# Portada / Inicio
# -------------------------
if st.session_state.pagina == "inicio":
    st.markdown(
        f"""
        <div class="hero">
          <div class="pill">✅ División igual o personalizada</div>
          <div class="pill">💱 Multi-moneda</div>
          <div class="pill">💳 Saldos y transferencias</div>
          <div class="pill">⬇️ Exportar CSV</div>
          <h1 style="margin-top:14px;">🌎 Viaje NYC – Amsterdam 2026</h1>
          <h3 style="margin-top:6px;">💸 Control de Gastos</h3>
          <p class="muted" style="margin-top:6px;">
            Cargá los gastos durante el viaje y obtené automáticamente quién le transfiere a quién.
          </p>
          <p class="small" style="margin-top:10px;">
            Personas: <b>{" · ".join(st.session_state.personas)}</b> · Moneda base: <b>{st.session_state.base_moneda}</b>
          </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write("")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        if st.button("🚀 Empezar", type="primary", use_container_width=True):
            st.session_state.pagina = "app"
            st.rerun()
    st.stop()

# -------------------------
# App principal
# -------------------------

st.title("💸 Gastos de Viaje")
st.caption("Cargá gastos, dividí y saldá fácil. (Versión clara)")

base = st.session_state.base_moneda
simbolo = {"ARS": "$", "USD": "US$", "EUR": "€"}[base]
personas = st.session_state.personas

tab1, tab2, tab3 = st.tabs(["➕ Cargar", "📋 Gastos", "🧾 Saldos"])

# =========================
# TAB 1 - CARGAR GASTO
# =========================
with tab1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("➕ Cargar gasto")

    with st.form("form_gasto", clear_on_submit=True):

        fecha = st.date_input("Fecha", value=date.today())
        concepto = st.text_input("Concepto", placeholder="Hotel, cena, Uber…")

        c1, c2 = st.columns(2)
        with c1:
            pago = st.selectbox("Pagó", personas)
        with c2:
            monto = st.number_input("Monto", min_value=0.0, value=0.0, step=1.0)

        c3, c4 = st.columns(2)
        with c3:
            moneda = st.selectbox("Moneda", [base, "USD", "EUR", "ARS"], index=0)
        with c4:
            cambio = st.number_input(
                f"Cambio a {base}",
                min_value=0.0,
                value=1.0 if moneda == base else 1000.0,
                step=0.1,
            )

        modo = st.radio("División", ["Igual", "Personalizada"], horizontal=True)

        partes = {}
        if modo == "Igual":
            for p in personas:
                partes[p] = monto / len(personas) if len(personas) else 0.0
            st.caption(f"Se divide igual entre {len(personas)}.")
        else:
            for p in personas:
                partes[p] = st.number_input(f"{p}", min_value=0.0, value=0.0, step=1.0, key=f"parte_{p}")

        submitted = st.form_submit_button("✅ Agregar gasto")

    if submitted:
        if not concepto.strip():
            st.error("Poné un concepto.")
        elif monto <= 0:
            st.error("El monto debe ser mayor a 0.")
        else:
            monto_base = normalize_currency(monto, cambio)

            row = {
                "id": str(uuid.uuid4()),
                "fecha": fecha.strftime("%Y-%m-%d"),
                "concepto": concepto.strip(),
                "pago": pago,
                "monto": float(monto),
                "moneda": moneda,
                "cambio_a_base": float(cambio),
                "monto_base": float(monto_base),
            }

            for p in personas:
                row[p] = round(float(normalize_currency(partes.get(p, 0.0), cambio)), 2)

            append_gasto_to_sheet(row, personas)

            st.success("Gasto agregado.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# TAB 2 - GASTOS
# =========================
with tab2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📋 Gastos")

    df = load_gastos_from_sheet(personas)

    if df.empty:
        st.info("Todavía no cargaste gastos.")
    else:
        resumen_cols = [c for c in ["fecha", "concepto", "pago", "monto_base"] if c in df.columns]
        st.dataframe(df[resumen_cols], use_container_width=True, hide_index=True)

        with st.expander("Ver detalle completo"):
            cols = ["fecha", "concepto", "pago", "monto", "moneda", "cambio_a_base", "monto_base"] + personas
            cols = [c for c in cols if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)

        b1, b2 = st.columns(2)

        with b1:
            if st.button("↩️ Borrar último", use_container_width=True):
                ws = get_ws()
                last_row = len(ws.get_all_values())
                if last_row > 1:
                    ws.delete_rows(last_row)
                    st.rerun()

        with b2:
            if st.button("✨ PDF Ejecutivo", use_container_width=True):
                pdf_path = generar_pdf_ejecutivo(df, personas, simbolo=simbolo, titulo="Viaje NYC – Amsterdam 2026")
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar PDF",
                        data=f,
                        file_name="informe_viaje_ejecutivo.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# TAB 3 - SALDOS
# =========================
with tab3:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🧾 Saldos y transferencias")

    df = load_gastos_from_sheet(personas)

    if not df.empty:
        total_base = df["monto_base"].sum()
        por_persona = total_base / len(personas)

        st.metric("Total", f"{simbolo}{total_base:,.2f}")
        st.metric("Por persona", f"{simbolo}{por_persona:,.2f}")

        balance = compute_balances(df, personas)
        bal_df = balance.reset_index()
        bal_df.columns = ["Persona", "Balance"]

        bal_df["Balance"] = bal_df["Balance"].apply(lambda x: f"{simbolo}{x:,.2f}")
        st.dataframe(bal_df, use_container_width=True, hide_index=True)

        st.subheader("💳 Quién le transfiere a quién")

        tx = settle_up(balance)
        if tx.empty:
            st.success("Todo saldado ✅")
        else:
            tx_show = tx.copy()
            tx_show["Monto"] = tx_show["Monto"].apply(lambda x: f"{simbolo}{x:,.2f}")
            st.dataframe(tx_show, use_container_width=True, hide_index=True)

    else:
        st.info("Cargá gastos para ver los saldos.")

    st.markdown("</div>", unsafe_allow_html=True)
