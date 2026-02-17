import streamlit as st
import pandas as pd
from datetime import date

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import fonts
from reportlab.lib.styles import getSampleStyleSheet
import os


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
    if df.empty:
        return pd.Series({p: 0.0 for p in personas})

    pagos = df.groupby("pago")["monto_base"].sum()
    partes = {p: df[p].sum() for p in personas if p in df.columns}

    balance = {}
    for p in personas:
        balance[p] = float(pagos.get(p, 0.0)) - float(partes.get(p, 0.0))
    return pd.Series(balance).sort_values(ascending=False)

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

    if st.button("🧹 Borrar todo", use_container_width=True):
        st.session_state.gastos = []
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

col1, col2 = st.columns([1.15, 1])

with col1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("➕ Cargar gasto")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        fecha = st.date_input("Fecha", value=date.today())
    with c2:
        concepto = st.text_input("Concepto", placeholder="Hotel, cena, Uber…")
    with c3:
        pago = st.selectbox("Pagó", personas)
    with c4:
        monto = st.number_input("Monto", min_value=0.0, value=0.0, step=1.0)

    c5, c6, c7 = st.columns([1, 1, 2])
    with c5:
        moneda = st.selectbox("Moneda", [base, "USD", "EUR", "ARS"], index=0)
    with c6:
        cambio = st.number_input(
            f"Cambio a {base}",
            min_value=0.0,
            value=1.0 if moneda == base else 1000.0,
            step=0.1,
            help=f"Si gastaste en {moneda} y tu base es {base}, poné cuánto vale 1 {moneda} en {base}."
        )
    with c7:
        modo = st.radio("División", ["Igual", "Personalizada"], horizontal=True)

    partes = {}
    if modo == "Igual":
        for p in personas:
            partes[p] = monto / len(personas) if len(personas) else 0.0
        st.info(f"Se divide igual entre {len(personas)}.")
    else:
        st.write("Cargá cuánto le corresponde a cada uno (en la moneda del gasto):")
        cols = st.columns(len(personas))
        for i, p in enumerate(personas):
            with cols[i]:
                partes[p] = st.number_input(f"{p}", min_value=0.0, value=0.0, step=1.0, key=f"parte_{p}")

        suma = sum(partes.values())
        if monto > 0 and abs(suma - monto) > 0.01:
            st.warning(f"⚠️ La suma de partes ({suma:.2f}) no coincide con el monto ({monto:.2f}).")

    if st.button("✅ Agregar gasto", type="primary", use_container_width=True):
        if not concepto.strip():
            st.error("Poné un concepto.")
        elif monto <= 0:
            st.error("El monto debe ser mayor a 0.")
        else:
            monto_base = normalize_currency(monto, cambio)
            row = {
                "fecha": str(fecha),
                "concepto": concepto.strip(),
                "pago": pago,
                "monto": float(monto),
                "moneda": moneda,
                "cambio_a_base": float(cambio),
                "monto_base": float(monto_base),
            }
            for p in personas:
                row[p] = normalize_currency(partes.get(p, 0.0), cambio)

            st.session_state.gastos.append(row)
            st.success("Gasto agregado.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📋 Gastos cargados")

    if st.session_state.gastos:
        df = pd.DataFrame(st.session_state.gastos)
        show = df[["fecha", "concepto", "pago", "monto", "moneda", "cambio_a_base", "monto_base"]].copy()
        show["monto_base"] = show["monto_base"].round(2)
        st.dataframe(show, use_container_width=True, hide_index=True)

        cA, cB = st.columns(2)
        with cA:
            if st.button("↩️ Borrar último", use_container_width=True):
                st.session_state.gastos.pop()
                st.rerun()
        with cB:
            st.download_button(
                "⬇️ Descargar CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="gastos_viaje.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.info("Todavía no cargaste gastos.")

    st.markdown("</div>", unsafe_allow_html=True)

st.write("")
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("🧾 Saldos y transferencias")

if st.session_state.gastos:
    df = pd.DataFrame(st.session_state.gastos)

    total_base = df["monto_base"].sum()
    por_persona = total_base / len(personas) if personas else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("Total (base)", money(total_base, simbolo))
    m2.metric("Por persona (base)", money(por_persona, simbolo))
    m3.metric("Gastos cargados", str(len(df)))

    balance = compute_balances(df, personas)
    bal_df = balance.reset_index()
    bal_df.columns = ["Persona", "Balance"]
    bal_df["Balance"] = bal_df["Balance"].apply(lambda x: money(x, simbolo))
    st.dataframe(bal_df, use_container_width=True, hide_index=True)
    st.caption("Balance > 0: le deben. Balance < 0: debe.")

    st.subheader("💳 Quién le transfiere a quién")
    tx = settle_up(balance)
    if tx.empty:
        st.success("✅ Está todo saldado (o casi).")
    else:
        tx_show = tx.copy()
        tx_show["Monto"] = tx_show["Monto"].apply(lambda x: money(x, simbolo))
        st.dataframe(tx_show, use_container_width=True, hide_index=True)
    if st.button("📄 Generar PDF resumen"):
          file_path = generar_pdf(df, balance, base)
          with open(file_path, "rb") as f:
               st.download_button(
                 label="⬇️ Descargar PDF",
                 data=f,
                 file_name="resumen_viaje.pdf",
                 mime="application/pdf"
                )

    
else:
    st.info("Cargá al menos un gasto para ver los saldos.")

st.markdown("</div>", unsafe_allow_html=True)
