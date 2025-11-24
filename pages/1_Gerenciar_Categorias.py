import sqlite3
import pandas as pd
import streamlit as st
import unicodedata
import time
from contextlib import closing
import os, hmac, hashlib


# CONFIG / CONSTANTES

DB_PATH = "/data/Gasto.db"  # ajuste para seu ambiente local se precisar
TABLE_GASTOS = "Gastos"  # nome da tabela de gastos

st.set_page_config(page_title="Gerência", page_icon="🛠️", layout="wide")

# LISTAS DE AJUDA
BLOCKED_CATS = {"VERIFICAR", "Outros", "OUTROS"}
EDITABLE_FIELDS = {"descricao", "categoria"}


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

# HELPERS


def _tamanho_util(txt: str) -> int:
    if not txt:
        return 0
    return sum(ch.isalnum() for ch in txt)


def normalizar_texto(txt: str) -> str:
    """Remove acentos e coloca em minúsculo para comparação."""
    if not txt:
        return ""
    txt = "".join(
        c
        for c in unicodedata.normalize("NFKD", txt)
        if not unicodedata.combining(c)
    )
    return txt.lower().strip()


# OPERACOES DE BANCO (COMUNS)


def conectar():
    return sqlite3.connect(DB_PATH)


def gastos_table_columns(conn, table):
    with closing(conn.cursor()) as cur:
        cur.execute(f'PRAGMA table_info("{table}")')
        cols = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return cols


def gastos_fetch_by_id(conn, table, row_id: int):
    """Busca um registro pelo ID (PK id)."""
    with closing(conn.cursor()) as cur:
        cur.execute(f'SELECT * FROM "{table}" WHERE id = ?', (int(row_id),))
        r = cur.fetchone()
        if not r:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, r))


def gastos_fetch_by_id_range(
    conn, table, start_id, end_id, limit=50, offset=0, order="DESC"
):
    """Busca um conjunto de registros por faixa de ID."""
    q = f'''
        SELECT *
          FROM "{table}"
         WHERE id BETWEEN ? AND ?
         ORDER BY id {order}
         LIMIT ? OFFSET ?
    '''
    with closing(conn.cursor()) as cur:
        cur.execute(q, (int(start_id), int(end_id), int(limit), int(offset)))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]


def gastos_update_row(conn, table, row_id, changes: dict):
    """Atualiza campos do registro pelo ID."""
    if not changes:
        return 0
    fields = ", ".join([f'"{k}" = ?' for k in changes.keys()])
    params = list(changes.values()) + [int(row_id)]
    with closing(conn.cursor()) as cur:
        cur.execute(f'UPDATE "{table}" SET {fields} WHERE id = ?', params)
        return cur.rowcount


def gastos_coerce_type(orig_val, new_val_str):
    """Para este painel só editamos strings (descricao, categoria)."""
    if new_val_str is None:
        return None
    s = str(new_val_str).strip()
    return None if s == "" else s


# ===== UI: EDITAR GASTOS =====
st.title("🛠️ Gerência")

st.header("Editar Gastos")

conn_g = conectar()
try:
    conn_g.row_factory = sqlite3.Row
except Exception:
    pass

# Confere se a tabela existe
with closing(conn_g.cursor()) as cur:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
        (TABLE_GASTOS,),
    )
    ok = cur.fetchone()

if not ok:
    st.error(f'A tabela "{TABLE_GASTOS}" não foi encontrada no banco.')
else:
    cols_info = gastos_table_columns(conn_g, TABLE_GASTOS)
    pk_name = "id"
    st.caption(f"Chave usada para edição: **{pk_name}**")

    tab_id, tab_range = st.tabs(["Editar por ID", "Pesquisar por Faixa de ID"])

    # -------- TAB: EDITAR POR ID --------
    with tab_id:
        st.subheader("Editar registro único")
        target_id = st.number_input("ID", min_value=1, step=1, value=1)
        if st.button("Carregar registro", type="primary"):
            st.session_state["_gasto_edit"] = gastos_fetch_by_id(
                conn_g, TABLE_GASTOS, int(target_id)
            )

        registro = st.session_state.get("_gasto_edit")
        if registro is None:
            st.info("Informe um ID e clique em **Carregar registro**.")
        else:
            if not registro:
                st.warning("Nenhum registro encontrado com esse ID.")
            else:
                st.caption(f"ID carregado: **{registro['id']}**")
                with st.form("form_edit_gasto"):
                    new_vals = {}
                    for c in cols_info:
                        name = c.get("name")
                        if not name:
                            continue

                        # PK travada
                        if name == pk_name:
                            st.text_input(
                                f"{name} (não editável)",
                                value=str(registro.get(name, "")),
                                disabled=True,
                            )
                            continue

                        orig = registro.get(name)
                        display_orig = "" if orig is None else str(orig)

                        if name in EDITABLE_FIELDS:
                            val_str = st.text_input(f"{name}", value=display_orig)
                            if val_str != display_orig:
                                new_vals[name] = val_str
                        else:
                            st.text_input(
                                f"{name}", value=display_orig, disabled=True
                            )

                    submitted = st.form_submit_button(
                        "Salvar alterações", type="primary"
                    )
                    if submitted:
                        diff = {}
                        for k, nv in new_vals.items():
                            if k not in EDITABLE_FIELDS:
                                continue
                            ov = registro.get(k)
                            if (
                                (ov is None and nv is not None)
                                or (ov is not None and nv is None)
                                or (ov != nv)
                            ):
                                diff[k] = nv
                        if not diff:
                            st.info("Nada para atualizar.")
                        else:
                            try:
                                with conn_g:
                                    rows = gastos_update_row(
                                        conn_g, TABLE_GASTOS, registro["id"], diff
                                    )
                                if rows == 1:
                                    st.success("Atualizado com sucesso.")
                                    st.session_state["_gasto_edit"] = gastos_fetch_by_id(
                                        conn_g, TABLE_GASTOS, registro["id"]
                                    )
                                else:
                                    st.warning("Nada foi alterado.")
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {e}")

    # -------- TAB: EDITAR POR FAIXA --------
    with tab_range:
        st.subheader("Lote leve (sem puxar a base toda)")
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col1:
            start_id = st.number_input(
                "ID inicial", min_value=1, value=1, step=1, key="start_id_r"
            )
        with col2:
            end_id = st.number_input(
                "ID final",
                min_value=int(start_id),
                value=int(start_id + 99),
                step=1,
                key="end_id_r",
            )
        with col3:
            page_size = st.selectbox(
                "Itens por página", [10, 25, 50], index=2, key="ps_r"
            )
        with col4:
            page = st.number_input(
                "Página", min_value=1, value=1, step=1, key="pg_r"
            )

        order = st.radio(
            "Ordenação por ID", ["DESC", "ASC"], horizontal=True, index=0, key="ord_r"
        )
        offset = (page - 1) * page_size

        if st.button("Pesquisar", type="primary", key="btn_search_r"):
            st.session_state["_range_rows"] = gastos_fetch_by_id_range(
                conn_g,
                TABLE_GASTOS,
                start_id,
                end_id,
                limit=page_size,
                offset=offset,
                order=order,
            )

        rows = st.session_state.get("_range_rows", [])
        if not rows:
            st.info("Nenhum resultado (ou ainda não pesquisou).")
        else:
            st.dataframe(rows, hide_index=True)
            id_opcoes = [r["id"] for r in rows]
            sel_id = st.selectbox("Escolha um ID para editar", id_opcoes)
            if st.button("Carregar seleção", key="load_sel_r"):
                st.session_state["_gasto_edit"] = gastos_fetch_by_id(
                    conn_g, TABLE_GASTOS, int(sel_id)
                )

            registro = st.session_state.get("_gasto_edit")
            if registro:
                st.divider()
                st.caption(f"Editando ID **{registro['id']}**")
                with st.form("form_edit_gasto_range"):
                    new_vals = {}
                    for c in cols_info:
                        name = c.get("name")
                        if not name:
                            continue

                        if name == pk_name:
                            st.text_input(
                                f"{name} (não editável)",
                                value=str(registro.get(name, "")),
                                disabled=True,
                            )
                            continue

                        orig = registro.get(name)
                        display_orig = "" if orig is None else str(orig)

                        if name in EDITABLE_FIELDS:
                            val_str = st.text_input(f"{name}", value=display_orig)
                            if val_str != display_orig:
                                new_vals[name] = val_str
                        else:
                            st.text_input(
                                f"{name}", value=display_orig, disabled=True
                            )

                    submitted = st.form_submit_button(
                        "Salvar alterações", type="primary"
                    )
                    if submitted:
                        diff = {}
                        for k, nv in new_vals.items():
                            if k not in EDITABLE_FIELDS:
                                continue
                            ov = registro.get(k)
                            if (
                                (ov is None and nv is not None)
                                or (ov is not None and nv is None)
                                or (ov != nv)
                            ):
                                diff[k] = nv
                        if not diff:
                            st.info("Nada a atualizar.")
                        else:
                            try:
                                with conn_g:
                                    rows = gastos_update_row(
                                        conn_g, TABLE_GASTOS, registro["id"], diff
                                    )
                                if rows == 1:
                                    st.success("Atualizado com sucesso.")
                                    st.session_state["_gasto_edit"] = gastos_fetch_by_id(
                                        conn_g, TABLE_GASTOS, registro["id"]
                                    )
                                    st.session_state[
                                        "_range_rows"
                                    ] = gastos_fetch_by_id_range(
                                        conn_g,
                                        TABLE_GASTOS,
                                        start_id,
                                        end_id,
                                        limit=page_size,
                                        offset=offset,
                                        order=order,
                                    )
                                else:
                                    st.warning("Nada foi alterado.")
                            except Exception as e:
                                st.error(f"Erro ao atualizar: {e}")

# fecha conexão local usada nessa seção
try:
    conn_g.close()
except Exception:
    pass


# ================= GERENCIAR CATEGORIAS =================

st.divider()
st.header("Editar Categorias")

# Atalho para recarregar dashboard
if st.sidebar.button("Atualizar agora"):
    st.cache_data.clear()
    st.rerun()


# --------- Tabela principal (CRUD) ---------
def carregar_categorias() -> pd.DataFrame:
    conn = conectar()
    df = pd.read_sql_query("SELECT * FROM Categorias", conn)
    conn.close()
    return df


def atualizar_categorias(df_editado: pd.DataFrame):
    conn = conectar()
    cur = conn.cursor()
    for _, row in df_editado.iterrows():
        cur.execute(
            """
            UPDATE Categorias
               SET palavra_chave = ?, categoria = ?
             WHERE id = ?
        """,
            (row["palavra_chave"], row["categoria"], row["id"]),
        )
    conn.commit()
    conn.close()


def sincronizar_gastos() -> int:
    """Atualiza Gastos.categoria via LIKE em descricao, ignorando bloqueadas e chaves curtas."""
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT palavra_chave, categoria FROM Categorias")
    categorias = [
        (pk, cat)
        for pk, cat in cur.fetchall()
        if (cat not in BLOCKED_CATS) and _tamanho_util(pk) >= 4
    ]

    atualizados = 0
    for palavra, cat in categorias:
        cur.execute(
            f"""
            UPDATE {TABLE_GASTOS}
               SET categoria = ?
             WHERE LOWER(descricao) LIKE LOWER(?)
        """,
            (cat, f"%{palavra}%"),
        )
        atualizados += cur.rowcount

    conn.commit()
    conn.close()
    return atualizados


def recategorizar_todos() -> int:
    """Reatribui 'categoria' em Gastos com base em Categorias (ignorando bloqueadas), só se mudar."""
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT palavra_chave, categoria FROM Categorias")
    categorias = [
        (pk, cat)
        for pk, cat in cur.fetchall()
        if (cat not in BLOCKED_CATS) and _tamanho_util(pk) >= 4
    ]

    cur.execute(f"SELECT id, descricao, categoria FROM {TABLE_GASTOS}")
    gastos = cur.fetchall()

    atualizados = 0
    for gid, desc, cat_atual in gastos:
        desc_norm = normalizar_texto(desc)
        nova_cat = None
        for palavra, cat in categorias:
            if normalizar_texto(palavra) in desc_norm:
                nova_cat = cat
                break
        if nova_cat and nova_cat != cat_atual:
            cur.execute(
                f"UPDATE {TABLE_GASTOS} SET categoria = ? WHERE id = ?",
                (nova_cat, gid),
            )
            atualizados += 1

    conn.commit()
    conn.close()
    return atualizados


def harmonizar_categorias():
    """
    Garante que toda categoria presente em Gastos exista em Categorias.
    - Não cria se for bloqueada (VERIFICAR/Outros) ou < 4 caracteres úteis.
    - Usa a própria categoria como palavra_chave (lower) e categoria (Title).
    Retorna (adicionadas, ignoradas).
    """
    conn = conectar()
    cur = conn.cursor()

    cur.execute(
        f"""
        SELECT DISTINCT g.categoria
          FROM {TABLE_GASTOS} g
          LEFT JOIN Categorias c ON c.categoria = g.categoria
         WHERE c.categoria IS NULL
           AND g.categoria IS NOT NULL
    """
    )
    faltantes = [r[0] for r in cur.fetchall()]

    adicionadas = 0
    ignoradas = 0

    for cat in faltantes:
        cat_str = (cat or "").strip()
        if (cat_str in BLOCKED_CATS) or (_tamanho_util(cat_str) < 4):
            ignoradas += 1
            continue

        cur.execute(
            """
            INSERT OR IGNORE INTO Categorias (palavra_chave, categoria)
            VALUES (?, ?)
        """,
            (cat_str.lower(), cat_str.title()),
        )
        if cur.rowcount > 0:
            adicionadas += 1

    conn.commit()
    conn.close()
    return adicionadas, ignoradas


def adicionar_categoria(palavra: str, categoria: str):
    """Adiciona nova categoria (bloqueia categorias reservadas e termos curtos)."""
    pk = (palavra or "").strip()
    cat = (categoria or "").strip()

    if (cat in BLOCKED_CATS) or (_tamanho_util(pk) < 4) or (_tamanho_util(cat) < 4):
        return

    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO Categorias (palavra_chave, categoria)
        VALUES (?, ?)
    """,
        (pk.lower(), cat.title()),
    )
    conn.commit()
    conn.close()


def excluir_palavra_chave(id_cat: str):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM Categorias WHERE id = ?", (id_cat,))
    conn.commit()
    conn.close()


def excluir_categoria(nome_cat: str, reclassificar: bool = False) -> int:
    """Remove TODAS as linhas da mesma categoria; se reclassificar=True, manda Gastos -> VERIFICAR."""
    conn = conectar()
    cur = conn.cursor()
    cur.execute("DELETE FROM Categorias WHERE categoria = ?", (nome_cat,))
    afetados = cur.rowcount
    if reclassificar:
        cur.execute(
            f"UPDATE {TABLE_GASTOS} SET categoria = 'VERIFICAR' WHERE categoria = ?",
            (nome_cat,),
        )
    conn.commit()
    conn.close()
    return afetados


# --------- Tabela principal (CRUD) ---------
st.subheader("📋 Categorias Cadastradas")
df_cat = carregar_categorias()

if df_cat.empty:
    st.warning("Nenhuma categoria cadastrada ainda.")
else:
    editadas = st.data_editor(
        df_cat,
        num_rows="fixed",
        key="cat_editor",
        hide_index=True,
        column_config={
            "palavra_chave": "🔑 Palavra-chave",
            "categoria": "🏷️ Categoria",
        },
    )

    if st.button("💾 Salvar alterações"):
        atualizar_categorias(editadas)
        atualizados = sincronizar_gastos()
        st.cache_data.clear()
        st.success(
            f"Categorias atualizadas com sucesso! ({atualizados} registros sincronizados em Gastos)"
        )
        time.sleep(2.5)
        st.rerun()

# --------- Adicionar nova categoria ---------
st.divider()
st.subheader("➕ Adicionar Nova Categoria")

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    nova_palavra = st.text_input("Palavra-chave (ex: giassi, steam, ifood)")
with col2:
    nova_categoria = st.text_input(
        "Nome da categoria (ex: Mercado, Jogos, Alimentação)"
    )

valida_palavra = _tamanho_util(nova_palavra) >= 4
valida_categoria = _tamanho_util(nova_categoria) >= 4

if nova_palavra and not valida_palavra:
    st.caption(
        "⚠️ A palavra-chave deve ter pelo menos 4 caracteres úteis (letras/números)."
    )
if nova_categoria and not valida_categoria:
    st.caption(
        "⚠️ O nome da categoria deve ter pelo menos 4 caracteres úteis (letras/números)."
    )

with col3:
    st.markdown("<div style='height:27px'></div>", unsafe_allow_html=True)
    add_disabled = not (valida_palavra and valida_categoria)
    if st.button("Adicionar", type="primary", disabled=add_disabled):
        adicionar_categoria(nova_palavra, nova_categoria)
        st.cache_data.clear()
        st.success(f"Categoria '{nova_categoria}' adicionada!")
        time.sleep(2.5)
        st.rerun()

# --------- Excluir palavra-chave (linha única) ---------
st.divider()
st.subheader("🗑️ Excluir palavra chave")

if not df_cat.empty:
    id_para_excluir = st.selectbox(
        "Selecione a palavra chave para excluir:",
        df_cat["id"].astype(str) + " - " + df_cat["palavra_chave"],
    )
    if st.button("Excluir"):
        id_cat = id_para_excluir.split(" - ")[0]
        excluir_palavra_chave(id_cat)
        st.cache_data.clear()
        st.warning("Palavra chave removida com sucesso!")
        time.sleep(2.5)
        st.rerun()

# --------- Excluir categoria inteira ---------
st.divider()
st.subheader("🧹 Excluir categoria inteira (todas as palavras-chave!)")

if not df_cat.empty:
    categorias_unicas = sorted(df_cat["categoria"].dropna().unique().tolist())
    cat_bulk = st.selectbox("Selecione a categoria:", categorias_unicas, key="bulk_cat")
    reclass = st.checkbox(
        "Reclassificar gastos dessa categoria para 'VERIFICAR'", value=True
    )
    if st.button("Excluir categoria inteira"):
        qtd = excluir_categoria(cat_bulk, reclassificar=reclass)
        st.cache_data.clear()
        st.warning(f"Removidas {qtd} palavras-chave da categoria '{cat_bulk}'.")
        if reclass:
            st.info("Todos os gastos dessa categoria foram marcados como 'VERIFICAR'.")
        time.sleep(2.5)
        st.rerun()

# --------- Reprocessar + Harmonizar ---------
st.divider()
st.subheader("🔁 Reprocessar categorias")

st.write(
    "Essa ação recategoriza os gastos e cria em 'Categorias' as categorias válidas "
    "que existirem em 'Gastos' e ainda não estiverem cadastradas."
)

if st.button("⚙️ Reprocessar todas as categorias"):
    with st.spinner("Reprocessando..."):
        total = recategorizar_todos()
        add, skip = harmonizar_categorias()

    st.cache_data.clear()
    st.success(f"✅ {total} registros recategorizados.")
    if add:
        st.info(
            f"➕ {add} categoria(s) criada(s) em 'Categorias' para alinhar com 'Gastos'."
        )
    if skip:
        st.warning(
            f"⚠️ {skip} categoria(s) ignoradas por serem bloqueadas ou < 4 caracteres."
        )
    time.sleep(2.5)
    st.rerun()

# --------- Corrigir 'VERIFICAR' ---------
st.divider()
st.subheader("🛠️ Corrigir gastos em 'VERIFICAR'")

conn = conectar()
df_ver = pd.read_sql_query(
    f"""
  SELECT id, data, descricao, valor, usuario, categoria
    FROM {TABLE_GASTOS}
   WHERE categoria = 'VERIFICAR'
ORDER BY data DESC
   LIMIT 500
""",
    conn,
)
conn.close()

if df_ver.empty:
    st.success("Sem pendências em 'VERIFICAR'.")
else:
    df_ver = df_ver.set_index("id", drop=True)

    try:
        cats = sorted(
            carregar_categorias()["categoria"].dropna().unique().tolist()
        )
        cats = [c for c in cats if c not in BLOCKED_CATS]
    except Exception:
        cats = []

    df_edit = st.data_editor(
        df_ver,
        hide_index=False,
        num_rows="fixed",
        column_config={
            "data": st.column_config.TextColumn("Data", disabled=True),
            "descricao": st.column_config.TextColumn("Descrição", disabled=True),
            "valor": st.column_config.NumberColumn(
                "Valor", disabled=True, step=0.01
            ),
            "usuario": st.column_config.TextColumn("Usuário", disabled=True),
            "categoria": (
                st.column_config.SelectboxColumn("Categoria", options=cats)
                if cats
                else st.column_config.TextColumn("Categoria")
            ),
        },
        key="ver_editor",
    )

    if st.button("Aplicar alterações"):
        changed_mask = df_edit["categoria"] != df_ver["categoria"]
        rows_to_update = df_edit[changed_mask]

        if rows_to_update.empty:
            st.info("Nada a atualizar.")
        else:
            conn = conectar()
            cur = conn.cursor()
            atualizados = 0
            for gid, row in rows_to_update.iterrows():
                new_cat = str(row["categoria"]).strip()
                if not new_cat or new_cat in BLOCKED_CATS:
                    continue
                cur.execute(
                    f"UPDATE {TABLE_GASTOS} SET categoria = ? WHERE id = ?",
                    (new_cat, int(gid)),
                )
                atualizados += 1
            conn.commit()
            conn.close()

            st.cache_data.clear()
            st.success(f"{atualizados} registro(s) recategorizado(s).")
            time.sleep(2.5)
            st.rerun()
