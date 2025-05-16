import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import date

# ─── 1. Conexão Supabase via secrets.toml ─────────────────────────────────────
url: str = st.secrets["supabase"]["url"]
key: str = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Relatório BNCC", layout="wide")
st.title("📊 Relatório de Desempenho BNCC")

# ─── Botão para recarregar dados (limpa cache apenas) ─────────────────────────
if st.button("🔄 Recarregar dados"):
    st.cache_data.clear()

# ─── 2. Formulário de inserção ─────────────────────────────────────────────────
with st.form("form_insercao", clear_on_submit=True):
    st.subheader("Novo registro")
    escola     = st.text_input("Escola")
    serie      = st.selectbox("Série", ["1º ano", "2º ano", "3º ano", "4º ano", "5º ano"])
    disciplina = st.selectbox("Disciplina", ["Português", "Matemática"])
    data       = st.date_input("Data", value=date.today())
    habilidade = st.text_input("Habilidade BNCC")
    resultado  = st.slider("Resultado (%)", 0, 100, 75)
    submitted  = st.form_submit_button("Adicionar")

    if submitted:
        supabase.table("relatorios_bncc").insert({
            "escola": escola,
            "serie": serie,
            "disciplina": disciplina,
            "data": data.isoformat(),
            "habilidade": habilidade,
            "resultado": resultado
        }).execute()
        st.success("✅ Registro adicionado!")
        # limpa o cache para que o próximo load traga o novo registro
        st.cache_data.clear()

# ─── 3. Função para carregar dados ──────────────────────────────────────────────
@st.cache_data
def carregar_dados():
    res = supabase.table("relatorios_bncc") \
                  .select("*") \
                  .order("data", desc=False) \
                  .execute()
    raw = res.data or []
    cols = ["id", "escola", "serie", "disciplina", "data", "habilidade", "resultado"]
    if not raw:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(raw)
    # Detecta e normaliza coluna de data
    date_col = next((c for c in df.columns if c.lower() == "data"), None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col])
        if date_col != "data":
            df = df.rename(columns={date_col: "data"})
    return df

# ─── 4. Carrega DataFrame e valida ─────────────────────────────────────────────
df = carregar_dados()
if df.empty:
    st.info("Nenhum dado cadastrado ainda.")
    st.stop()

# ─── 5. Filtro de intervalo de datas ───────────────────────────────────────────
st.sidebar.subheader("🔎 Filtrar por intervalo de datas")
min_date = df["data"].min().date()
max_date = df["data"].max().date()

start_date = st.sidebar.date_input(
    "Data Inicial", min_value=min_date, value=min_date, max_value=max_date
)
end_date = st.sidebar.date_input(
    "Data Final", min_value=min_date, value=max_date, max_value=max_date
)

if start_date > end_date:
    st.sidebar.error("Data Inicial deve ser anterior ou igual à Data Final")
    st.stop()
else:
    df = df[(df["data"] >= pd.to_datetime(start_date)) &
            (df["data"] <= pd.to_datetime(end_date))]

# ─── 6. Cálculo de tendência ──────────────────────────────────────────────────
grp = df.groupby(["escola", "serie", "disciplina", "habilidade"])
primeiro = grp.first().reset_index()[["escola", "serie", "disciplina", "habilidade", "resultado"]]
ultimo   = grp.last().reset_index()[["escola", "serie", "disciplina", "habilidade", "resultado"]]
tend = pd.merge(
    primeiro, ultimo,
    on=["escola", "serie", "disciplina", "habilidade"],
    suffixes=("_primeiro", "_ultimo")
)
tend["variacao_%"] = (
    (tend["resultado_ultimo"] - tend["resultado_primeiro"])
    / tend["resultado_primeiro"] * 100
).round(2)

# ─── 7. Exibição dos resultados ───────────────────────────────────────────────
st.subheader("Tendência de Desempenho por Habilidade")
st.dataframe(tend)

st.subheader("Evolução ao Longo do Tempo")
col1, col2 = st.columns(2)
with col1:
    sel_hab = st.selectbox("Habilidade", df["habilidade"].unique().tolist())
with col2:
    sel_esc = st.selectbox("Escola", df["escola"].unique().tolist())

filtrado = df[(df["habilidade"] == sel_hab) & (df["escola"] == sel_esc)]
chart_df = filtrado.set_index("data")[["resultado"]]
st.line_chart(chart_df)
