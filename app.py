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

# ─── Abas ────────────────────────────────────────────────────────────────────
tab_main, tab_cadastro = st.tabs(["📊 Dashboard", "⚙️ Cadastro"])

# ─── Funções auxiliares ──────────────────────────────────────────────────────
@st.cache_data
def load_list(table: str, column: str):
    res = supabase.table(table).select(column).order(column).execute()
    return [r[column] for r in res.data] if res.data else []

@st.cache_data
def carregar_dados():
    res = supabase.table("relatorios_bncc").select("*").order("data", desc=False).execute()
    df = pd.DataFrame(res.data or [])
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
    return df

# ─── Aba Dashboard ──────────────────────────────────────────────────────────
with tab_main:
    if st.button("🔄 Recarregar dados", key="reload_main"):
        st.cache_data.clear()

    df = carregar_dados()
    st.subheader("➕ Novo(s) registro(s) de resultado por Construtor")
    if "entries" not in st.session_state:
        st.session_state.entries = []
    # Campos um abaixo do outro, exceto construtor+resultado lado a lado
    escola = st.selectbox("Escola", load_list("escolas", "nome"))
    serie = st.selectbox("Série", [f"{i}º ano" for i in range(1,10)])
    disciplina = st.selectbox("Disciplina", ["Português", "Matemática"])
    data = st.date_input("Data", value=date.today())
    c1, c2 = st.columns([3,1])
    new_con = c1.selectbox("Construtor", load_list("construtores", "nome"), key="new_con_main")
    new_res = c2.slider("%", 0, 100, 75, key="new_res_main")
    if c2.button("➕", key="add_main"):
        st.session_state.entries.append({"construtor": new_con, "resultado": new_res})

    # Buffer
    if st.session_state.entries:
        st.markdown("**Buffer de lançamentos:**")
        for idx, row in enumerate(st.session_state.entries):
            colA, colB = st.columns([8,1])
            colA.write(f"- **{row['construtor']}** → {row['resultado']}%")
            if colB.button("❌", key=f"rem_main_{idx}"):
                st.session_state.entries.pop(idx)
                break
        if st.button("✅ Cadastrar registros", key="submit_main"):
            for row in st.session_state.entries:
                supabase.table("relatorios_bncc").insert({
                    "escola": escola,
                    "serie": serie,
                    "disciplina": disciplina,
                    "data": data.isoformat(),
                    "resultado": row["resultado"],
                    "construtor": row["construtor"]
                }).execute()
            st.success(f"✅ {len(st.session_state.entries)} registros adicionados!")
            st.session_state.entries = []
            st.cache_data.clear()

    if df.dropna(how="all", subset=["escola","construtor","resultado"]).empty:
        st.info("Nenhum dado cadastrado ainda.")
    else:
        # Filtros
        st.sidebar.subheader("🔎 Filtros")
        f_esc = st.sidebar.selectbox("Filtrar por Escola", ["Todas"] + load_list("escolas","nome"))
        min_d, max_d = df["data"].min().date(), df["data"].max().date()
        start_d = st.sidebar.date_input("Data Inicial", value=min_d, min_value=min_d, max_value=max_d)
        end_d   = st.sidebar.date_input("Data Final",   value=max_d, min_value=min_d, max_value=max_d)
        if start_d > end_d:
            st.sidebar.error("Data Inicial deve ser ≤ Data Final")
            st.stop()
        df_f = df[(df["data"]>=pd.to_datetime(start_d)) & (df["data"]<=pd.to_datetime(end_d))]
        if f_esc != "Todas":
            df_f = df_f[df_f["escola"]==f_esc]

        # KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("🔢 Total lançamentos", len(df_f))
        c2.metric("📈 Média Geral", f"{round(df_f['resultado'].mean(),2)}%")
        ts = df_f.groupby(["escola","data"])["resultado"].mean().reset_index(name="média_result")
        fl = ts.groupby("escola").agg(
            primeiro=("média_result","first"),
            ultimo=("média_result","last"),
            count=("média_result","size")
        ).reset_index()
        fl = fl[fl['count']>=2]
        fl['variacao_%'] = ((fl['ultimo']-fl['primeiro'])/fl['primeiro']*100).round(2)
        c3.metric("⚖️ Média Variação", f"{round(fl['variacao_%'].mean(),2)}%")

        # Top 10
        st.subheader("🏆 Top 10 Bom Desempenho (média ≥ 50%)")
        avg_s = df_f.groupby('escola')['resultado'].mean().reset_index(name='média_result')
        best = avg_s[avg_s['média_result']>=50].nlargest(10,'média_result')
        bar1 = alt.Chart(best).mark_bar().encode(
            x='média_result:Q', y=alt.Y('escola:N', sort='-x')
        )
        st.altair_chart(bar1 + bar1.mark_text(align='left', dx=3).encode(text='média_result:Q'),
                        use_container_width=True)

        st.subheader("⚠️ Top 10 a Melhorar (média < 50%)")
        worst = avg_s[avg_s['média_result']<50].nsmallest(10,'média_result')
        bar2 = alt.Chart(worst).mark_bar(color='firebrick').encode(
            x='média_result:Q', y=alt.Y('escola:N', sort='x')
        )
        st.altair_chart(bar2 + bar2.mark_text(align='left', dx=3).encode(text='média_result:Q'),
                        use_container_width=True)

        # Português vs Matemática
        st.subheader("📈 Português vs Matemática")
        cmp = df_f.groupby(['data','disciplina'])['resultado'].mean().reset_index()
        chart = alt.Chart(cmp).mark_line(point=True).encode(
            x=alt.X('data:T', title='Data'),
            y=alt.Y('resultado:Q', title='Resultado (%)'),
            color='disciplina:N'
        )
        st.altair_chart(chart, use_container_width=True)

        # Evolução detalhada por filtros
        st.subheader("📈 Evolução Detalhada")
        fc1, fc2, fc3 = st.columns(3)
        fe = fc1.selectbox("Escola", sorted(df_f['escola'].unique()), key='evo_esc')
        series_opts = sorted(df_f[df_f['escola']==fe]['serie'].unique())
        fs = fc2.selectbox("Série", series_opts, key='evo_ser')
        con_opts = sorted(df_f[(df_f['escola']==fe)&(df_f['serie']==fs)]['construtor'].unique())
        fcon = fc3.selectbox("Construtor", con_opts, key='evo_con')
        sel = df_f[(df_f['escola']==fe)&(df_f['serie']==fs)&(df_f['construtor']==fcon)]
        line = alt.Chart(sel).mark_line(point=True).encode(
            x=alt.X('data:T', title='Data'),
            y=alt.Y('resultado:Q', title='Resultado (%)')
        )
        txt = line.mark_text(align='center', dy=-10).encode(text='resultado:Q')
        st.altair_chart(line + txt, use_container_width=True)

# ─── Aba Cadastro ────────────────────────────────────────────────────────────
with tab_cadastro:
    st.subheader("⚙️ Gestão de Cadastros")
    subt = st.tabs(["Escolas","Construtores"])

    with subt[0]:
        esc = load_list("escolas","nome")
        st.dataframe(pd.DataFrame({"nome": esc}))
        new_esc = st.text_input("Nova Escola", key="inp_esc")
        if st.button("➕ Adicionar Escola", key="add_esc") and new_esc:
            supabase.table("escolas").insert({"nome": new_esc}).execute()
            st.success("Escola adicionada.")
            st.cache_data.clear()
        for i, nome in enumerate(esc):
            c1, c2 = st.columns([8,1])
            c1.write(nome)
            if c2.button("❌", key=f"del_esc_{i}"):
                supabase.table("escolas").delete().eq("nome", nome).execute()
                st.success("Escola removida.")
                st.cache_data.clear()

    with subt[1]:
        cons = load_list("construtores","nome")
        st.dataframe(pd.DataFrame({"nome": cons}))
        new_con2 = st.text_input("Novo Construtor", key="inp_con")
        if st.button("➕ Adicionar Construtor", key="add_con") and new_con2:
            supabase.table("construtores").insert({"nome": new_con2}).execute()
            st.success("Construtor adicionado.")
            st.cache_data.clear()
        for i, nome in enumerate(cons):
            c1, c2 = st.columns([8,1])
            c1.write(nome)
            if c2.button("❌", key=f"del_con_{i}"):
                supabase.table("construtores").delete().eq("nome", nome).execute()
                st.success("Construtor removido.")
                st.cache_data.clear()
