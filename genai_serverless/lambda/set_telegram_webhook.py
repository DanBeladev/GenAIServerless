import os
import requests


def handler(event, context):
    try:
        function_url = event['ResourceProperties']['FunctionUrl']
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        response = requests.get(f'https://api.telegram.org/bot{telegram_token}/setWebhook?url={function_url}')
        print(f"response: {response}")
        return {
            'statusCode': 200,
            'body': response
        }
    except Exception as e:
        error_message = str(e)
        print(f"Error: {error_message}")
        return {
            'statusCode': 500,
            'body': error_message
        }
