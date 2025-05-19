import streamlit as st
import pandas as pd
import altair as alt
from supabase import create_client, Client
from datetime import date
from httpx import ConnectTimeout

# ─── 1. Conexão Supabase ──────────────────────────────────────────────────────
url: str = st.secrets["supabase"]["url"]
key: str = st.secrets["supabase"]["key"]
try:
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"❌ Não foi possível conectar ao Supabase:\n{e}")
    st.stop()

st.set_page_config(page_title="Relatório BNCC (Construtor)", layout="wide")
st.title("📊 Relatório de Desempenho BNCC (por Construtor)")

# ─── 2. Botão para limpar cache ───────────────────────────────────────────────
if st.button("🔄 Recarregar dados"):
    st.cache_data.clear()

# ─── 3. Carregar listas ──────────────────────────────────────────────────────
@st.cache_data
def load_list(table: str, column: str):
    try:
        res = supabase.table(table).select(column).order(column).execute()
        return [r[column] for r in res.data] if res.data else []
    except ConnectTimeout:
        st.error(f"❌ Timeout ao buscar dados de `{table}`.")
        st.stop()
    except Exception as e:
        st.error(f"❌ Erro ao buscar `{table}`: {e}")
        st.stop()

escolas     = load_list("escolas", "nome")
construtores= load_list("construtores", "nome")

# ─── 4. Carregar dados ────────────────────────────────────────────────────────
@st.cache_data
def carregar_dados():
    try:
        res = supabase.table("relatorios_bncc").select("*").order("data", desc=False).execute()
    except ConnectTimeout:
        st.error("❌ Timeout ao buscar registros em `relatorios_bncc`.")
        st.stop()
    except Exception as e:
        st.error(f"❌ Erro ao buscar `relatorios_bncc`: {e}")
        st.stop()

    raw = res.data or []
    expected = ["id","escola","serie","disciplina","data","resultado","construtor"]
    df = pd.DataFrame(raw)
    for col in expected:
        if col not in df.columns:
            df[col] = None
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    return df

df = carregar_dados()

# ─── 5. Buffer de lançamentos ─────────────────────────────────────────────────
if "entries" not in st.session_state:
    st.session_state.entries = []

st.subheader("➕ Novo(s) registro(s) de resultado por Construtor")
escola     = st.selectbox("Escola", escolas)
serie      = st.selectbox("Série", [f"{i}º ano" for i in range(1,10)])
disciplina = st.selectbox("Disciplina", ["Português", "Matemática"])
data       = st.date_input("Data", value=date.today())

col1, col2, col3 = st.columns([3,3,1])
with col1:
    new_con = st.selectbox("Construtor", construtores, key="new_con")
with col2:
    new_res = st.slider("Resultado (%)", 0, 100, 75, key="new_res")
with col3:
    if st.button("➕", help="Adicionar construtor ao buffer"):
        st.session_state.entries.append({"construtor": new_con, "resultado": new_res})

if st.session_state.entries:
    st.markdown("**Buffer de lançamentos:**")
    for idx, row in enumerate(st.session_state.entries):
        c1, c2 = st.columns([8,1])
        c1.write(f"- **{row['construtor']}** → {row['resultado']}%")
        if c2.button("❌", key=f"rem_{idx}"):
            st.session_state.entries.pop(idx)
            break

if st.session_state.entries and st.button("✅ Cadastrar registros"):
    errors = []
    for row in st.session_state.entries:
        try:
            supabase.table("relatorios_bncc").insert({
                "escola": escola,
                "serie": serie,
                "disciplina": disciplina,
                "data": data.isoformat(),
                "resultado": row["resultado"],
                "construtor": row["construtor"]
            }).execute()
        except Exception as e:
            errors.append(f"{row['construtor']}: {e}")
    if errors:
        st.error("Alguns lançamentos falharam:\n" + "\n".join(errors))
    else:
        st.success(f"✅ {len(st.session_state.entries)} registros adicionados!")
    st.session_state.entries = []
    st.cache_data.clear()

# ─── 6. Sem dados ────────────────────────────────────────────────────────────
if df.dropna(how="all", subset=["escola","construtor","resultado"]).empty:
    st.info("Nenhum dado cadastrado. Use o formulário acima.")
    st.stop()

# ─── 7. Filtro de período e escola ────────────────────────────────────────────
st.sidebar.subheader("🔎 Filtros")
# Novo filtro por escola na sidebar
f_esc = st.sidebar.selectbox("Filtrar por Escola", ["Todas"] + escolas)
st.sidebar.markdown("---")
min_date, max_date = df["data"].min().date(), df["data"].max().date()
start_date = st.sidebar.date_input("Data Inicial", value=min_date, min_value=min_date, max_value=max_date)
end_date   = st.sidebar.date_input("Data Final",   value=max_date, min_value=min_date, max_value=max_date)

# Validação e aplicação dos filtros
if start_date > end_date:
    st.sidebar.error("Data Inicial deve ser ≤ Data Final")
    st.stop()

df = df[(df["data"] >= pd.to_datetime(start_date)) & (df["data"] <= pd.to_datetime(end_date))]
if f_esc != "Todas":
    df = df[df["escola"] == f_esc]

# ─── 8. KPIs ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("🔢 Total lançamentos", len(df))
c2.metric("📈 Média Geral", f"{round(df['resultado'].mean(),2)}%")

# ─── 9. Prepara série temporal e média por escola ────────────────────────────
school_ts = df.groupby(["escola","data"])["resultado"].mean().reset_index(name="média_result")
first_last = school_ts.groupby("escola").agg(
    primeiro=("média_result","first"),
    ultimo  =("média_result","last"),
    count   =("média_result","size")
).reset_index()
first_last = first_last[first_last["count"]>=2]
first_last["variacao_%"] = ((first_last["ultimo"]-first_last["primeiro"]) / first_last["primeiro"] *100).round(2)
c3.metric("⚖️ Média Variação", f"{round(first_last['variacao_%'].mean(),2)}%")

# ─── 10. Top 10 Melhores (média ≥ 50%) ────────────────────────────────────────
st.subheader("🏆 Top 10 Escolas de Bom Desempenho (média ≥ 50%)")
avg_school = df.groupby("escola")["resultado"].mean().reset_index(name="média_result")
best = avg_school[avg_school["média_result"]>=50].nlargest(10, "média_result")
bar_best = alt.Chart(best).mark_bar().encode(
    x="média_result:Q", y=alt.Y("escola:N", sort="-x")
)
text_best = bar_best.mark_text(align="left", dx=3).encode(text="média_result:Q")
st.altair_chart(bar_best + text_best, use_container_width=True)

# ─── 11. Top 10 a Melhorar (média < 50%) ──────────────────────────────────────
st.subheader("⚠️ Top 10 Escolas a Melhorar (média < 50%)")
worst = avg_school[avg_school["média_result"]<50].nsmallest(10, "média_result")
bar_worst = alt.Chart(worst).mark_bar(color="firebrick").encode(
    x="média_result:Q", y=alt.Y("escola:N", sort="x")
)
text_worst = bar_worst.mark_text(align="left", dx=3).encode(text="média_result:Q")
st.altair_chart(bar_worst + text_worst, use_container_width=True)

# ─── 12. Média por Construtor ────────────────────────────────────────────────
st.subheader("🔧 Média por Construtor")
avg_con = df.groupby("construtor")["resultado"].mean().reset_index(name="média_result")
bar_con = alt.Chart(avg_con).mark_bar().encode(
    x="média_result:Q", y=alt.Y("construtor:N", sort="-x")
)
text_con = bar_con.mark_text(align="left", dx=3).encode(text="média_result:Q")
st.altair_chart(bar_con + text_con, use_container_width=True)

# ─── 13. Evolução Detalhada ──────────────────────────────────────────────────
st.subheader("📈 Evolução Detalhada por Filtros")
fc1, fc2, fc3 = st.columns(3)
f2_esc = fc1.selectbox("Escola",     sorted(df["escola"].unique()), key="evo_esc")
f2_ser = fc2.selectbox("Série",      sorted(df["serie"].unique()), key="evo_ser")
f2_con = fc3.selectbox("Construtor", sorted(df["construtor"].unique()), key="evo_con")

filt = df[
    (df["escola"]    ==f2_esc)&
    (df["serie"]     ==f2_ser)&
    (df["construtor"]==f2_con)
]
line = alt.Chart(filt).mark_line(point=True).encode(x="data:T", y="resultado:Q")
text4 = line.mark_text(align="center", dy=-10).encode(text="resultado:Q")
st.altair_chart(line + text4, use_container_width=True)
