import pika
import json
import os

def publish_to_queue(products):
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq-service-deploy')
    rabbitmq_user = os.getenv('RABBITMQ_USER', 'admin')
    rabbitmq_password = os.getenv('RABBITMQ_PASSWORD', 'admin')
    queue_name = os.getenv('QUEUE_NAME', 'product_queue')

    credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)
    connection_params = pika.ConnectionParameters(
        host=rabbitmq_host,
        port=5672,
        credentials=credentials
    )

    connection = pika.BlockingConnection(connection_params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    for product in products:
        message = json.dumps(product)
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)  
        )

    print("✅ Mensajes publicados con éxito.")
    connection.close()
