from flask import  jsonify, request, Blueprint
from src.views.producer import publish_to_queue
import pandas as pd


upload_excel_blueprint = Blueprint('ingest-service', __name__)

# endpoint create User
@upload_excel_blueprint.route('/ingest/upload-excel', methods = ['POST'])
def products_bull_creation():



    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    


    # Cargar el archivo Excel
    df = pd.read_excel(file)

    # Validar que el archivo tenga las columnas necesarias
    required_columns = {"name", "price", "quantity"}
    if not required_columns.issubset(df.columns):
        return jsonify({"error": f"El archivo debe contener las columnas: {required_columns}"}), 400
    
    
    # Convertir DataFrame a JSON y enviarlo a la cola
    records = df.to_dict(orient='records')
    publish_to_queue(records)

    return jsonify({"message": f"Se enviaron {len(records)} productos a la cola"}), 200




# endpoint health check service
@upload_excel_blueprint.route('/ingest/ping', methods=['GET'])
def ping():
    return 'pong', 200









