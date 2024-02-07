import json
import os
from urllib import parse

import requests
from langchain_openai.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory(memory_key="chat_history")


def extract_message(event: dict) -> str:
    body = json.loads(event['body'])
    return body.get("message", {}).get("text", "")


def invoke_model(question: str) -> str:
    """Invokes the language model."""
    llm = OpenAI(temperature=0)
    template = """You are a nice chatbot having a conversation with a human.

    Previous conversation:
    {chat_history}

    New human question: {question}
    Response:"""
    prompt = PromptTemplate.from_template(template)
    conversation = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=memory
    )
    model_response = conversation({"question": question})
    return model_response["text"]


def create_response(message: str) -> dict:
    """Creates HTTP response object."""
    return {
        'statusCode': 200,
        'body': json.dumps({'message': message})
    }


def send_telegram_message(message: str) -> None:
    """Sends message to Telegram."""
    print(f'sending message to Telegram: {message}')
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    # Split the response into chunks of 4096 characters
    message_chunks = [message[i:i + 4096] for i in range(0, len(message), 4096)]
    for chunk in message_chunks:
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
        error_message = str(e)
        print(f"Error: {error_message}")
        send_telegram_message(error_message)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': error_message})
        }
