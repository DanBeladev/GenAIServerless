import json
import os
from urllib import parse

import requests
from langchain_openai.llms import OpenAI


def extract_message(event) -> str:
    body = json.loads(event['body'])
    message = body["message"]["text"]
    return message


def invoke_model(message):
    llm = OpenAI(temperature=0.9)  # model_name="text-davinci-003"
    model_response: str = llm.invoke(input=message)
    print(f"model_response: {model_response}")
    return model_response


def create_response(model_response: str) -> dict:
    response = {
        'statusCode': 200,
        'body': json.dumps({'message': model_response})
    }
    return response


def send_telegram_message(response: str) -> None:
    print(f'sending message to telegram: {response}')
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    # Split the response into chunks of 4096 characters
    response_chunks = [response[i:i + 4096] for i in range(0, len(response), 4096)]
    for chunk in response_chunks:
        if chunk.strip():
            encoded_chunk = parse.quote_plus(chunk)
            print(f'encoded chunk: {encoded_chunk}')
            api_url = f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}>&text={encoded_chunk}'
            print(f'api => {api_url}')
            send_message_response = requests.post(api_url)
            print(f'send_message_response: {send_message_response.text}')


def handler(event, context):
    try:
        message: str = extract_message(event)
        model_response: str = invoke_model(message)
        send_telegram_message(model_response)
        response: dict = create_response(model_response)
        return response
    except Exception as e:
        print(f"Error: {e}")
        send_telegram_message(str(e))
        return {
            'statusCode': 500,
            'body': json.dumps({'message': str(e)})
        }
