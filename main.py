from flask import Flask, request, jsonify
import sys

# Desativa buffering globalmente 
sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)

@app.route('/')
def home():
    return "API Gastos online ✅"

@app.route('/notificacaos', methods=['POST'])
def receber_notificacao():
    data = request.get_json(silent=True)  # evita erro se JSON malformado

    if not data:
        return jsonify({"erro": "Nenhum JSON válido recebido"}), 400

    print("📩 Notificação recebida:", data, flush=True)  # imprime imediatamente

    # Reenvia o mesmo JSON que recebeu para fins de teste
    return jsonify({
        "status": "ok",
        "recebido": data
    }), 200
