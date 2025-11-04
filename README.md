# VITOR — Gastos (API + Dashboard)

> É um rastreador de gastos com **API Flask** + **Dashboard Streamlit** + **SQLite**.  
> Deploy em **Fly.io** com **processos separados** (`app` e `dash`) e **volume** para persistência.

---

## 🧭 Visão Geral

- **API (`app`)** recebe gastos (ex.: do listener de notificações Android) e grava em SQLite.
- **Dashboard (`dash`)** para gestão: categorias, recategorização e **edição pontual** de registros.
- **Banco**: `Gasto.db` com tabelas `Gastos` e `Categorias`.


### Stack
- Python 3.11+
- Flask (API)
- Streamlit (Dashboard)
- SQLite3
- Fly.io (máquinas, processos e volumes)

## 🗂️ Banco de Dados

### Esquema atual

```sql
-- Gastos
CREATE TABLE IF NOT EXISTS Gastos (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  data      TEXT,           -- ISO 8601: YYYY-MM-DD HH:MM:SS
  descricao TEXT,
  valor     REAL,
  categoria TEXT,
  usuario   TEXT
);

CREATE INDEX IF NOT EXISTS idx_gastos_data      ON Gastos(data);
CREATE INDEX IF NOT EXISTS idx_gastos_categoria ON Gastos(categoria);

-- Categorias (regras simples)
CREATE TABLE IF NOT EXISTS Categorias (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  palavra_chave  TEXT NOT NULL,
  categoria      TEXT NOT NULL,
  UNIQUE (palavra_chave, categoria) ON CONFLICT IGNORE
);
```

- **Categorias bloqueadas**: `VERIFICAR`, `Outros`, `OUTROS` (não viram regras).
- **Regra mínima**: `palavra_chave` com **≥ 4** caracteres úteis.



---

## 🔌 API (Flask)

### POST `/add_gasto`
Recebe um gasto e grava.

**Body JSON**
```json
{
  "descricao": "mercado",
  "valor": 114.30,
  "categoria": "Necessario",
  "usuario": "Conjunto",
  "data": "2025-11-03T15:40:22"
}
```

**Regra de data no servidor (`main.py`)**:
```python
from datetime import datetime
data_envio = data.get("data", datetime.now().isoformat()).split(".")[0].replace("T", " ")
```

**Extras**
- Se `categoria` vier vazia, pode cair em `VERIFICAR` para ajuste posterior no dashboard.

---

## 📊 Dashboard (Streamlit)

### Gerência ▸ Categorias
- CRUD de `Categorias` (com validação de tamanho).
- Botão **“Reprocessar”**:
  - recategorização de `Gastos` por match de `palavra_chave` em `descricao` (ignora bloqueadas).
  - **harmonização**: cria em `Categorias` o que aparece em `Gastos` (respeitando regras).

### Gerência ▸ Corrigir “VERIFICAR”
- Lista últimos pendentes.
- **Editável somente**: `categoria` (o resto travado para não quebrar nada).

### Gerência ▸ Editar Gastos (por ID / faixa)
- **Editáveis**: `descricao`, `categoria`.
- **Travados**: `valor`, `usuario`, `data`, `id`.
- Busca por **ID real** (PK `id`; não confunda com gaps de `ROWID`).

> Se você mexer em `valor`, aceite o risco. A versão atual do painel trava de propósito.

---

## ▶️ Rodando Local

```bash
python -m venv .venv && . .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

# API
python main.py

# Dashboard (outra aba)
streamlit run Dashboard.py --server.port 8080 --server.address 0.0.0.0
```

**Variáveis úteis**
- `DB_PATH` padrão: `Gasto.db` (ajuste para `/data/Gasto.db` em produção).
- Porta do Streamlit: `8080`.

---

## 🚢 Fly.io (resumo prático)

### `fly.toml` (exemplo mínimo)
```toml
[processes]
  app  = "python main.py"
  dash = "streamlit run Dashboard.py --server.port 8080 --server.address 0.0.0.0"


```

### Comandos úteis
```bash
# Deploy
fly deploy

# Escalas
fly scale count 1 -g app          # sobe só o app
fly scale count 0 -g dash         # deixa o dash desligado
fly scale count 1 -g dash -r gru  # liga o dash quando precisar (mesma região do volume)

# Volume
fly volumes list
# NUNCA use --with-new-volumes se quiser reaproveitar o existente
```

### Troca de banco no volume (sem dor)
```bash
# helper machine temporária
fly machine run alpine:3.20 -r <REGIAO> -v <VolumeID>:/data -m fly_process_group=maint -n helper -- sleep infinity
fly ssh sftp put --select <MachineIDEXTRA> ./Gasto.db /data/Gasto.db.tmp
fly ssh console --select <MachineIDEXTRA> -C "mv -f /data/Gasto.db.tmp /data/Gasto.db && chmod 664 /data/Gasto.db && sync"
fly machine destroy <MachineIDEXTRA>
```

> Se quiser impedir que o deploy crie máquina do `dash`, antes do deploy:
> ```bash
> fly scale count 0 -g dash
> fly deploy
> ```


## 📜 Licença
Uso pessoal. Faça o que quiser, mas não venha chorar se quebrar.

---

## 💡 Roadmap v3 (ideias)
- Token/HMAC por dispositivo (whitelist).
- `categoria_id` com FK para `Categorias`.
- Regras por regex e/ou priorização de match.
- Integração por Webhooks/APIs bancárias quando disponível.

---

## Disclamer 
- Utilizado auxilio e geração por IA para realizar o projeto
