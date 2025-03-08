from flask import Flask, jsonify
from src.views.ingest_routes import upload_excel_blueprint


app = Flask(__name__)
app_context = app.app_context()
app_context.push()


app.register_blueprint(upload_excel_blueprint)

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=3001)