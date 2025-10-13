from flask import Flask, request, jsonify
import sys, re, os
from datetime import datetime
import sqlite3

# Desativa buffering globalmente (para log ao vivo no Fly)
sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/data/Gasto.db"

app = Flask(__name__)

# Conexao com banco de dados
def conectar():
    os.makedirs("/data", exist_ok=True)
    return sqlite3.connect(DB_PATH)

# Identifica o usuário com base no app.
def user(datau: str) -> str:
    mapping = {
        "com.nu.production": "Pessoal",
        "br.com.intermedium": "Conjunto"
        
    }
    return mapping.get(datau, datau)


def criar_ou_atualizar_tabela():
    """Cria tabelas, se ainda não existirem."""
    with conectar() as conn:
        cur = conn.cursor()

        # Tabela principal de gastos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS Gastos (
            data TEXT,
            categoria TEXT,
            valor REAL,
            descricao TEXT,
            usuario TEXT
        )
        """)

        # Tabela de categorias com mapeamento de palavras-chave
        cur.execute("""
        CREATE TABLE IF NOT EXISTS Categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palavra_chave TEXT UNIQUE,
            categoria TEXT
        )
        """)

        conn.commit()

# CATEGORIZAÇÃO AUTOMÁTICA

def identificar_categoria(descricao):
    """
    Identifica a categoria de um gasto com base na descrição.
    Se não houver correspondência, cria uma nova categoria automaticamente.
    """
    descricao_lower = descricao.lower()
    with conectar() as conn:
        cur = conn.cursor()

        # Busca categorias existentes
        cur.execute("SELECT palavra_chave, categoria FROM Categorias")
        categorias = cur.fetchall()

        # Tenta encontrar uma correspondência
        for palavra, cat in categorias:
            if palavra.lower() in descricao_lower:
                return cat

        # Se não encontrou, cria uma nova categoria baseada na descrição
        nova_cat = descricao.strip().title() 
        try:
            cur.execute("""
                INSERT OR IGNORE INTO Categorias (palavra_chave, categoria)
                VALUES (?, ?)
            """, (nova_cat.lower(), nova_cat))
            conn.commit()
            print(f"Nova categoria criada: {nova_cat}", flush=True)
        except Exception as e:
            print(f"Erro ao criar nova categoria: {e}", flush=True)

        return nova_cat



# --- Inicialização ---



@app.route('/')
def home():
    return "API Gastos online"

@app.route('/notificacaos', methods=['POST'])
def receber_notificacao():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"erro": "Nenhum JSON válido recebido"}), 400

    titulo = data.get ("titulo", "")
    mensagem = data.get("mensagem", "")   
    app_origem = data.get("app", "")
    data_envio = data.get("data", datetime.now().isoformat()).split('.')[0]
    
    if "Compra" not in titulo :
        print(f"Ignorado: título '{titulo}' não é uma compra aprovada.", flush=True)
        return jsonify({"status": "ignorado", "motivo": "Título não corresponde a compra"}), 200

    if "Recusada" in titulo :
        print(f"Ignorado: título '{titulo}' é uma compra recusada.", flush=True)
        return jsonify({"status": "ignorado", "motivo": "Titulo de compra recusada"}), 200


    usuario = user(app_origem)

    
    padrao_valor = re.search(r"R\$ ?(\d{1,7}(?:\.\d{3})*,\d{2})", mensagem)
    valor = float(padrao_valor.group(1).replace(".", "").replace(",", ".")) if padrao_valor else None

    # Extrai o local (palavra após "em")
    padrao_local = re.search(r"em ([A-Z0-9\s]+?)(?:\.|,|\*|$)", mensagem)
    descricao = padrao_local.group(1).strip() if padrao_local else "Nao identificado"
    
    # Identifica (ou cria) categoria com base na descrição
    categoria = identificar_categoria(descricao)

    registro = {
        "data": data_envio,
        "categoria": categoria,
        "valor": valor,
        "descricao": descricao,
        "usuario": usuario
    }

    try:
        with conectar() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO Gastos (data, categoria, valor, descricao, usuario)
                VALUES (?, ?, ?, ?, ?)
            """, (registro["data"], registro["categoria"], registro["valor"], registro["descricao"], registro["usuario"]))
            conn.commit()

            # Busca os 3 últimos registros
            cur.execute("""
                SELECT data, categoria, valor, descricao, usuario
                FROM Gastos
                ORDER BY rowid DESC LIMIT 3
            """)
            ultimos = cur.fetchall()

        ultimos_json = [
            {"data": u[0], "categoria": u[1], "valor": u[2], "descricao": u[3], "usuario": u[4]}
            for u in ultimos
        ]

        print("Registro salvo:", registro, flush=True)
        return jsonify({"status": "ok", "registro": registro, "ultimos": ultimos_json}), 200

    except Exception as e:
        print("Erro ao salvar:", e, flush=True)
        return jsonify({"erro": f"Falha ao salvar no banco: {e}"}), 500




if __name__ == '__main__':
    criar_ou_atualizar_tabela()
    app.run(host='0.0.0.0', port=8080)
    
