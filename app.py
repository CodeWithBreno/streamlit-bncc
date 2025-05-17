import streamlit as st
import pandas as pd
import altair as alt
from supabase import create_client, Client
from datetime import date

# ─── 1. Conexão Supabase via secrets ───────────────────────────────────────────
url: str = st.secrets["supabase"]["url"]
key: str = st.secrets["supabase"]["key"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Relatório BNCC", layout="wide")
st.title("📊 Relatório de Desempenho BNCC")

# ─── Botão para limpar cache (recarregar dados) ────────────────────────────────
if st.button("🔄 Recarregar dados"):
    st.cache_data.clear()

# ─── 2. Formulário de inserção ─────────────────────────────────────────────────
with st.form("form_insercao", clear_on_submit=True):
    st.subheader("➕ Novo registro")
    escola     = st.text_input("Escola")
    serie      = st.selectbox("Série", [f"{i}º ano" for i in range(1,10)])
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
        st.cache_data.clear()

# ─── 3. Carregar dados ─────────────────────────────────────────────────────────
@st.cache_data
def carregar_dados():
    res = supabase.table("relatorios_bncc") \
                  .select("*") \
                  .order("data", desc=False) \
                  .execute()
    raw = res.data or []
    cols = ["id","escola","serie","disciplina","data","habilidade","resultado"]
    if not raw:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(raw)
    # normaliza coluna data
    date_col = next((c for c in df.columns if c.lower()=="data"), None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col])
        if date_col!="data":
            df = df.rename(columns={date_col:"data"})
    return df

df = carregar_dados()
if df.empty:
    st.info("Nenhum dado cadastrado ainda.")
    st.stop()

# ─── 4. Filtro de intervalo de datas ───────────────────────────────────────────
st.sidebar.subheader("🔎 Período de análise")
min_date, max_date = df["data"].min().date(), df["data"].max().date()
start_date = st.sidebar.date_input("Data Inicial", value=min_date, min_value=min_date, max_value=max_date)
end_date   = st.sidebar.date_input("Data Final",   value=max_date, min_value=min_date, max_value=max_date)
if start_date > end_date:
    st.sidebar.error("Data Inicial deve ser ≤ Data Final")
    st.stop()
df = df[(df["data"] >= pd.to_datetime(start_date)) & (df["data"] <= pd.to_datetime(end_date))]

# ─── 5. Cálculo de tendência ──────────────────────────────────────────────────
grp = df.groupby(["escola","serie","disciplina","habilidade"])
first = grp.first().reset_index()[["escola","serie","disciplina","habilidade","resultado"]]
last  = grp.last().reset_index()[["escola","serie","disciplina","habilidade","resultado"]]
tend  = pd.merge(first, last,
                 on=["escola","serie","disciplina","habilidade"],
                 suffixes=("_primeiro","_ultimo"))
tend["variacao_%"] = ((tend["resultado_ultimo"] - tend["resultado_primeiro"])
                     / tend["resultado_primeiro"] * 100).round(2)

# ─── 6. KPI Cards ─────────────────────────────────────────────────────────────
col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("🔢 Total Registros", len(df))
with col_b:
    avg_perf = round(df["resultado"].mean(),2)
    st.metric("📈 Média de Resultado", f"{avg_perf}%")
with col_c:
    avg_var = round(tend["variacao_%"].mean(),2) if not tend.empty else 0
    st.metric("⚖️ Média de Variação", f"{avg_var}%")

# ─── 7. Top 10 Escolas ─────────────────────────────────────────────────────────
st.subheader("🏆 Top 10 Escolas por Evolução Média")
top10 = (
    tend.groupby("escola")["variacao_%"]
        .mean()
        .sort_values(ascending=False)
        .head(10)
        .reset_index(name="média_variacao_%")
)
# Altair bar chart com rótulos
bar = (
    alt.Chart(top10)
    .mark_bar()
    .encode(x=alt.X("média_variacao_%:Q", title="Variação Média (%)"),
            y=alt.Y("escola:N", sort="-x", title="Escola"))
)
text = bar.mark_text(
    align="left", dx=3
).encode(text="média_variacao_%:Q")
st.altair_chart(bar + text, use_container_width=True)

# ─── 8. Heatmap Habilidade × Série ────────────────────────────────────────────
st.subheader("🗺️ Heatmap: Média de Resultado por Habilidade e Série")
pivot = df.pivot_table(
    index="habilidade", columns="serie", values="resultado", aggfunc="mean"
).reset_index().melt(id_vars="habilidade", var_name="serie", value_name="média_resultado")
heat = (
    alt.Chart(pivot)
    .mark_rect()
    .encode(
        x=alt.X("serie:N", title="Série"),
        y=alt.Y("habilidade:N", title="Habilidade"),
        color=alt.Color("média_resultado:Q", scale=alt.Scale(scheme="lightmulti")),
        tooltip=["habilidade","serie","média_resultado"]
    )
)
st.altair_chart(heat, use_container_width=True)

# ─── 9. Distribuição de Resultados ────────────────────────────────────────────
st.subheader("📊 Distribuição de Resultados (%)")
dist = df["resultado"].value_counts().sort_index().reset_index()
dist.columns = ["resultado","contagem"]
bar2 = (
    alt.Chart(dist)
    .mark_bar()
    .encode(x=alt.X("resultado:O", title="Resultado (%)"),
            y=alt.Y("contagem:Q", title="Frequência"))
)
text2 = bar2.mark_text(
    dy=-5
).encode(text="contagem:Q")
st.altair_chart(bar2 + text2, use_container_width=True)

# ─── 10. Benchmark Português vs Matemática ────────────────────────────────────
st.subheader("🔍 Benchmark: Português vs Matemática")
bench = (
    df.groupby(["data","disciplina"])["resultado"]
      .mean()
      .reset_index()
)
line1 = (
    alt.Chart(bench)
    .mark_line(point=True)
    .encode(x="data:T", y="resultado:Q", color="disciplina:N")
)
text3 = line1.mark_text(
    align="center", dy=-10
).encode(text="resultado:Q")
st.altair_chart(line1 + text3, use_container_width=True)

# ─── 11. Evolução Filtrada ────────────────────────────────────────────────────
st.subheader("📈 Evolução por Filtros")
col1, col2, col3 = st.columns(3)
with col1:
    sel_hab   = st.selectbox("Habilidade", sorted(df["habilidade"].unique()))
with col2:
    sel_esc   = st.selectbox("Escola",     sorted(df["escola"].unique()))
with col3:
    sel_serie = st.selectbox("Série",      sorted(df["serie"].unique()))

filt = df[
    (df["habilidade"]==sel_hab) &
    (df["escola"]    ==sel_esc) &
    (df["serie"]     ==sel_serie)
]
line2 = (
    alt.Chart(filt)
    .mark_line(point=True)
    .encode(x="data:T", y="resultado:Q")
)
text4 = line2.mark_text(
    align="center", dy=-10
).encode(text="resultado:Q")
st.altair_chart(line2 + text4, use_container_width=True)
