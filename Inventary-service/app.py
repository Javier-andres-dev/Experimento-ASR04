import os
import json
import uuid
import time
import threading
import pika
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from flask import Flask, Response, jsonify
from concurrent.futures import ThreadPoolExecutor
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
import logging
from pythonjsonlogger import jsonlogger

# 🔹 Configuración de logging estructurado
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(fmt="%(asctime)s %(levelname)s %(message)s")
logHandler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logHandler)

app = Flask(__name__)
NUM_THREADS = 4  
executor = ThreadPoolExecutor(max_workers=NUM_THREADS)

first_record_time = None
last_record_time = None
lock = threading.Lock()

# 🔹 Pool de conexiones a PostgreSQL
DB_POOL = pool.SimpleConnectionPool(
    minconn=1, 
    maxconn=NUM_THREADS * 2,  
    host=os.getenv('DB_HOST'),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)

def get_db_connection():
    """Obtiene una conexión del pool."""
    return DB_POOL.getconn()

def release_db_connection(conn):
    """Devuelve la conexión al pool."""
    DB_POOL.putconn(conn)

# 🔹 Métricas de Prometheus
REQUEST_COUNT = Counter('requests_total', 'Total de peticiones recibidas')
INSERTION_COUNT = Counter('insertions_total', 'Total de registros insertados en PostgreSQL')
INSERTION_TIME = Histogram('insertion_duration_seconds', 'Tiempo en segundos de inserciones en PostgreSQL')
MESSAGES_PROCESSED = Counter('rabbitmq_messages_processed', 'Total de mensajes procesados desde RabbitMQ')

# 🔹 Nueva métrica para medir tiempo total desde la primera hasta la última inserción
TOTAL_PROCESSING_TIME = Gauge('total_processing_time_seconds', 'Tiempo total de procesamiento desde el primer hasta el último registro')

@app.route("/inventary/ping", methods=["GET"])
def health_check():
    return 'pong', 200

@app.route("/inventary/metrics", methods=["GET"])
def metrics():
    """Expone métricas en formato Prometheus"""
    return Response(generate_latest(REGISTRY), mimetype="text/plain")

def save_to_db(records):
    global first_record_time, last_record_time

    if isinstance(records, dict):
        records = [records]

    with lock:
        if first_record_time is None:
            first_record_time = time.time()

    start_time = time.time()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = "INSERT INTO products (id, name, price, quantity) VALUES %s"
        values = [(str(uuid.uuid4()), rec["name"], rec["price"], rec["quantity"]) for rec in records]

        psycopg2.extras.execute_values(cur, query, values)
        conn.commit()

        # 🔹 Incrementar el contador de inserciones
        INSERTION_COUNT.inc(len(records))

    except Exception as e:
        logger.error({"message": f"❌ Error insertando en DB: {e}"})
        conn.rollback()
    finally:
        cur.close()
        release_db_connection(conn)

    end_time = time.time()
    elapsed_time = end_time - start_time

    # 🔹 Registrar el tiempo de inserción
    INSERTION_TIME.observe(elapsed_time)

    with lock:
        last_record_time = end_time

        # 🔹 Actualizar la métrica con el tiempo total de ejecución
        total_execution_time = last_record_time - first_record_time
        TOTAL_PROCESSING_TIME.set(total_execution_time)

    logger.info({"message": f"✅ Insertados {len(records)} registros en {elapsed_time:.4f} segundos"})

def process_message(body):
    global first_record_time, last_record_time

    try:
        records = json.loads(body)
        logger.info({"message": f"📥 Procesando {len(records) if isinstance(records, list) else 1} registros en un hilo..."})
        
        save_to_db(records)

        # 🔹 Incrementar el contador de mensajes procesados
        MESSAGES_PROCESSED.inc()

        with lock:
            if first_record_time and last_record_time:
                total_execution_time = last_record_time - first_record_time
                logger.info({"message": f"⏱️ Tiempo total de ejecución desde el primer hasta el último registro: {total_execution_time:.4f} segundos"})

    except Exception as e:
        logger.error({"message": f"❌ Error procesando mensaje: {e}"})

def callback(ch, method, properties, body):
    executor.submit(process_message, body)
    ch.basic_ack(delivery_tag=method.delivery_tag)

def consume():
    while True:
        try:
            logger.info({"message": "🔄 Conectando a RabbitMQ..."})

            rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq-service-deploy')
            rabbitmq_user = os.getenv('RABBITMQ_USER', 'admin')
            rabbitmq_password = os.getenv('RABBITMQ_PASSWORD', 'admin')
            queue_name = os.getenv('QUEUE_NAME', 'product_queue')

            credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)

            connection_params = pika.ConnectionParameters(
                host=rabbitmq_host,
                port=5672,
                credentials=credentials,
                heartbeat=600
            )

            connection = pika.BlockingConnection(connection_params)
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)

            channel.basic_qos(prefetch_count=NUM_THREADS * 2)
            channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

            logger.info({"message": "✅ Consumidor listo, esperando mensajes..."})
            channel.start_consuming()

        except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
            logger.error({"message": f"⚠️ Conexión fallida: {str(e)}. Reintentando en 5 segundos..."})
            time.sleep(5)

def start_flask():
    app.run(host="0.0.0.0", port=3002)

if __name__ == "__main__": 
    threading.Thread(target=start_flask, daemon=True).start()
    consume()
