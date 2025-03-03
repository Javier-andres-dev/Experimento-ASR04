import pika
import json
import os


def publish_to_queue(products):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq_broker'))
    channel = connection.channel()
    channel.queue_declare(queue='product_queue', durable=True)

    for product in products:
        message = json.dumps(product)
        channel.basic_publish(
            exchange='',
            routing_key='product_queue',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)  # Mensajes persistentes
        )

    connection.close()
