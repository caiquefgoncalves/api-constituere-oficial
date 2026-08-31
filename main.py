from flask import Flask, send_from_directory, jsonify, request, make_response
from flask_cors import CORS
import os

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://172.20.10.13:5173",
    "http://10.92.11.35:5173",
    "http://10.92.11.4:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.18.218:5173"
]

CORS(app,
     origins=ALLOWED_ORIGINS,
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Access-Token"],
     expose_headers=["Content-Type", "Authorization", "X-Access-Token"])


@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", request.headers.get('Origin', ''))
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Access-Token')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        return response


app.config.from_pyfile('config.py')


app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'Usuarios'), exist_ok=True)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)



from usuario import *
from funcao import *

if __name__ == '__main__':
    print("\n=== ROTAS REGISTRADAS ===")
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith('/static'):
            print(f"{list(rule.methods)} {rule.rule}")
    print("=========================\n")

    app.run(host='0.0.0.0', port=5000, debug=True)