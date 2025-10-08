from flask import Flask, request

app = Flask(__name__)

@app.route('/')
def home():
    return "API Gastos online ✅"

@app.route('/notificacaos', methods=['POST'])
def receber_notificacao():
    data = request.json
    print("Notificação recebida:", data)
    return {"status": "ok"}, 200
