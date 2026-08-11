from flask import Flask, send_from_directory, jsonify, request, make_response
from flask_cors import CORS
import os

app = Flask(__name__)
ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

CORS(app, origins=ALLOWED_ORIGINS, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], supports_credentials=True)


@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return make_response(), 200


app.config.from_pyfile('config.py')

# Criação das pastas de upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'Usuarios'), exist_ok=True)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# Importação das rotas
from usuario import *
from funcao import *

if __name__ == '__main__':
    print("\n=== ROTAS REGISTRADAS ===")
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/static'):
            print(f"{list(rule.methods)} {rule.rule}")
    print("=========================\n")

    app.run(host='0.0.0.0', port=5000, debug=True)