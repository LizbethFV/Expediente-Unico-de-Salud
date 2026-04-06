from flask import Flask, request, jsonify
from pymongo import MongoClient
import os

app = Flask(__name__)

# Conexión a tu MongoDB de Dokploy
# Usamos variables de entorno para seguridad
MONGO_URI = os.getenv("MONGO_URL", "mongodb://apiuser:Proyecto_pp_api@localhost:27017/admin")
client = MongoClient(MONGO_URI)
db = client['expediente_salud']

@app.route('/')
def home():
    return "<h1>Servidor del Expediente Único de Salud Activo</h1><p>Perfil: Doctores / Pacientes<
@app.route('/api/pacientes', methods=['POST'])
def agregar_paciente():
    datos = request.json
    # Estructura básica: nombre, edad, historial
    nuevo_id = db.pacientes.insert_one(datos).inserted_id
    return jsonify({"status": "success", "id": str(nuevo_id)}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
