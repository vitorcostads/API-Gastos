from flask import Flask, request, jsonify
import datetime



app = Flask(__name__)

@app.route('/notificacaoS', methods=['POST'])
def receber_notificacao():
    data = request.json
    mensagem = data.get("mensagem", "")
    hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Temporário: salva num log
    with open("notificacoes_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{hora}] {mensagem}\n")

    print(f"Nova notificação: {mensagem}")
    return jsonify({"status": "ok", "mensagem": mensagem}), 200

@app.route('/')
def home():
    return "API Gastos está online!"


if __name__ == '__main__':

    app.run(host='0.0.0.0', port=5000)
