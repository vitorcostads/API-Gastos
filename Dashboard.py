import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import os, hmac, hashlib

DB_PATH = "/data/Gasto.db"  # caminho local do banco

# CONFIGURAÇÃO DE PÁGINA

st.set_page_config(
    page_title="Dashboard de Gastos",
    page_icon="💸",
    layout="wide"
)

def _hash_pwd(salt: str, pwd: str) -> str:
    return hashlib.sha256((salt + pwd).encode()).hexdigest()

def _check_credentials(user: str, pwd: str) -> bool:
    exp_user = os.environ.get("DASH_USER", "")
    salt = os.environ.get("DASH_SALT", "")
    exp_hash = os.environ.get("DASH_PASS_HASH", "")
    if not exp_user or not salt or not exp_hash:
        # Se você esquecer de setar variáveis, bloqueia geral
        return False
    ok_user = hmac.compare_digest(user, exp_user)
    ok_pwd = hmac.compare_digest(_hash_pwd(salt, pwd), exp_hash)
    return ok_user and ok_pwd

def require_login():
    
    if st.session_state.get("auth_ok"):
        return

    st.title("🔐 Login")
    with st.form("login"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        sub = st.form_submit_button("Entrar")
    if sub:
        if _check_credentials(u, p):
            st.session_state["auth_ok"] = True
            # Streamlit >= 1.30
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        else:
            st.error("Credenciais inválidas.")

    st.stop() 

def logout_button():
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()
            

require_login()
logout_button()


# FUNÇÃO DE LEITURA

@st.cache_data
def carregar_dados():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    df_gastos = pd.read_sql_query("SELECT * FROM Gastos", conn)
    df_cat = pd.read_sql_query("SELECT * FROM Categorias", conn)
    conn.close()
    return df_gastos, df_cat


# CARREGAMENTO

st.title("💸 Dashboard de Gastos Pessoais")

try:
    df_gastos, df_cat = carregar_dados()
except Exception as e:
    st.error(f"Erro ao carregar o banco: {e}")
    st.stop()

if df_gastos.empty:
    st.warning("Nenhum dado encontrado no banco de dados.")
    st.stop()


# PRÉ-PROCESSAMENTO

df_gastos["data"] = pd.to_datetime(df_gastos["data"], errors="coerce")
df_gastos["mes"] = df_gastos["data"].dt.to_period("M").astype(str)

# ATUALIZAÇÃO MANUAL

if st.sidebar.button("Atualizar agora"):
    st.cache_data.clear()
    st.rerun() 



# FILTROS

st.sidebar.subheader("Visualização")

modo_pizza = st.sidebar.toggle("Exibir gráfico de pizza", value=False)
tipo_grafico = "Pizza" if modo_pizza else "Barras"

st.sidebar.divider()

st.sidebar.header("Filtros")

usuarios = ["Todos"] + sorted(df_gastos["usuario"].dropna().unique().tolist())
usuario_sel = st.sidebar.selectbox("Usuário", usuarios)

categorias = ["Todas"] + sorted(df_gastos["categoria"].dropna().unique().tolist())
categoria_sel = st.sidebar.selectbox("Categoria", categorias)

meses = ["Todos"] + sorted(df_gastos["mes"].dropna().unique().tolist())
mes_sel = st.sidebar.selectbox("Mês", meses)

# APLICA FILTROS

df_filtrado = df_gastos.copy()
if usuario_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["usuario"] == usuario_sel]
if categoria_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado["categoria"] == categoria_sel]
if mes_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["mes"] == mes_sel]



# MÉTRICAS RÁPIDAS

col1, col2, col3 = st.columns(3)
col1.metric("Total gasto", f"R$ {df_filtrado['valor'].sum():,.2f}")
col2.metric("Média por compra", f"R$ {df_filtrado['valor'].mean():,.2f}")
col3.metric("Total de compras", len(df_filtrado))


# GRÁFICOS

st.subheader("Gastos por categoria")

cat_sum = df_filtrado.groupby("categoria", as_index=False)["valor"].sum().sort_values("valor", ascending=False)


if tipo_grafico == "Barras":
    fig1 = px.bar(
        cat_sum,
        x="categoria",
        y="valor",
        color="categoria",
        text=cat_sum["valor"].apply(lambda v: f"R$ {v:,.2f}"),
        title="Distribuição de gastos"
    )
    
    fig1.update_layout(
        xaxis_title="Categoria",
        yaxis_title="Valor (R$)",
        uniformtext_mode = 'hide',
        uniformtext_minsize = 15,
        showlegend=False)
    
    fig1.update_traces(
        hovertemplate="Gasto total: R$ %{value:,.2f}<extra></extra>",
        textposition = "inside",
        insidetextanchor="middle",
        
        )
else:
    fig1 = px.pie(
        cat_sum,
        names="categoria",
        values="valor",
        title="Distribuição de gastos",
        hole=0.5
        
    )
    fig1.update_traces(
        hovertemplate="Gasto total: R$ %{value:,.2f}",
        textinfo="percent+label", pull=[0.05]*len(cat_sum)
        )

st.plotly_chart(fig1, use_container_width=True)

st.subheader("Gastos por mês")
mes_sum = df_filtrado.groupby("mes", as_index=False)["valor"].sum()
fig2 = px.line(mes_sum, x="mes", y="valor", title="Evolução mensal")
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Histórico de compras")
st.dataframe(df_filtrado.sort_values("data", ascending=False))

