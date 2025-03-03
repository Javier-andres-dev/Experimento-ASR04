import os
import json
import uuid
import time
import threading
import pika
import psycopg2
import psycopg2.extras
from concurrent.futures import ThreadPoolExecutor
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, start_http_server

# Definir número de hilos
NUM_THREADS = 4 
executor = ThreadPoolExecutor(max_workers=NUM_THREADS)

# Definir métricas de Prometheus
PROCESSED_MESSAGES = Counter("processed_messages_total", "Número de mensajes procesados")
DB_INSERT_TIME = Histogram("db_insert_duration_seconds", "Tiempo de inserción en la base de datos")
EXECUTION_TIME = Gauge("db_execution_time_seconds", "Tiempo total de ejecución desde el primer hasta el último registro")  # Nueva métrica

# Variables globales para el tiempo de ejecución
first_record_time = None
last_record_time = None
lock = threading.Lock()  # Para evitar condiciones de carrera

def save_to_db(records):
    """Guarda registros en PostgreSQL de manera masiva y mide el tiempo entre el primer y el último registro."""
    global first_record_time, last_record_time

    if isinstance(records, dict):
        records = [records]  # Convertir un solo registro en lista

    with lock:  # Proteger las variables globales
        if first_record_time is None:
            first_record_time = time.time()  # Guardar la hora del primer registro

    start_time = time.time()  # ⏳ Marcar el inicio de la inserción

    with DB_INSERT_TIME.time():  # Medir tiempo con Prometheus
        try:
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST'), database=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD')
            )
            cur = conn.cursor()

            query = "INSERT INTO products (id, name, price, quantity) VALUES %s"
            values = [(str(uuid.uuid4()), rec["name"], rec["price"], rec["quantity"]) for rec in records]

            psycopg2.extras.execute_values(cur, query, values)

            conn.commit()
            cur.close()
            conn.close()

            end_time = time.time()  # ⏳ Marcar el final de la inserción
            elapsed_time = end_time - start_time  # ⏳ Calcular duración de la inserción

            with lock:
                last_record_time = end_time  # Registrar la hora del último registro

            PROCESSED_MESSAGES.inc(len(records))  # Contador de registros procesados
            print(f"✅ Insertados {len(records)} registros en {elapsed_time:.4f} segundos")

        except Exception as e:
            print(f"❌ Error insertando en la base de datos: {e}")

def process_message(body):
    """Procesa cada mensaje recibido de RabbitMQ en un hilo separado."""
    global first_record_time, last_record_time

    try:
        records = json.loads(body)
        print(f"📥 Procesando {len(records) if isinstance(records, list) else 1} registros en un hilo...")
        save_to_db(records)

        # Si es el último mensaje, calcular el tiempo total de ejecución
        with lock:
            if first_record_time and last_record_time:
                total_execution_time = last_record_time - first_record_time
                EXECUTION_TIME.set(total_execution_time)  # Actualizar métrica en Prometheus
                print(f"⏱️ Tiempo total de ejecución desde el primer hasta el último registro: {total_execution_time:.4f} segundos")

    except Exception as e:
        print(f"❌ Error procesando mensaje: {e}")

def callback(ch, method, properties, body):
    """Recibe los mensajes de RabbitMQ y los procesa en múltiples hilos."""
    executor.submit(process_message, body)  # Enviar la tarea a un hilo
    ch.basic_ack(delivery_tag=method.delivery_tag)  # Confirmar que el mensaje fue procesado

def consume():
    """Escucha la cola de RabbitMQ y procesa mensajes de manera continua."""
    while True:
        try:
            print("🔄 Conectando a RabbitMQ...")
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=os.getenv('RABBITMQ_HOST'), heartbeat=600))
            channel = connection.channel()
            channel.queue_declare(queue=os.getenv('QUEUE_NAME'), durable=True)

            channel.basic_qos(prefetch_count=NUM_THREADS)
            channel.basic_consume(queue=os.getenv('QUEUE_NAME'), on_message_callback=callback)

            print("✅ Consumidor de RabbitMQ listo, esperando mensajes...")
            channel.start_consuming()
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
            print(f"⚠️ Conexión con RabbitMQ fallida: {str(e)}. Reintentando en 5 segundos...")
            time.sleep(5)

def metrics():
    """Devuelve las métricas en formato Prometheus."""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

if __name__ == "__main__":
    start_http_server(8001)  # Exponer métricas en el puerto 8001
    consume()  # Iniciar el consumidor de RabbitMQ
