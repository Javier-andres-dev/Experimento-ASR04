from flask import  jsonify, request, Blueprint
from src.views.producer import publish_to_queue
import pandas as pd
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST


REQUEST_COUNT = Counter("requests_total", "Número total de solicitudes")
PROCESS_TIME = Histogram("process_duration_seconds", "Tiempo de procesamiento de archivos")


upload_excel_blueprint = Blueprint('upload-excel', __name__)

# endpoint create User
@upload_excel_blueprint.route('/upload-excel', methods = ['POST'])
def products_bull_creation():

    REQUEST_COUNT.inc()

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    with PROCESS_TIME.time():
      try:
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
      except Exception as e:
          return jsonify({"error": str(e)}), 500


@upload_excel_blueprint.route('/metrics', methods=['GET'])
def metrics():
    """Devuelve las métricas en formato Prometheus."""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


# endpoint health check service
@upload_excel_blueprint.route('/upload-excel/ping', methods=['GET'])
def ping():
    return 'pong', 200









