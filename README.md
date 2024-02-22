How To Build a Serverless LangChain-Powered Telegram Q&A Bot

LangChain is a framework for developing applications powered by language models that you can use to create your own LangChain-based Telegram bot.
I will share some personal insights I have learned from creating my own Telegram bot, along with a template for creating a Serverless application using AWS CDK and LangChain. You can use the template in its entirety or in parts. We will also introduce a private Telegram channel that you can use to ask questions and receive answers from an AI model customized to suit your needs.

Create a Serverless Application Using AWS CDK as IaC
For this purposes of this post, we focus on implementing a Serverless application using AWS CDK as infrastructure as code (IaC), rather than the design or handling of all security issues.

An flow diagram and architecture
Before we get started on this, however, you’ll need:

An AWS account
The AWS CDK Toolkit (for this post, I used version 2.118.0)
Python 3.11 or above
An OpenAI API key
Configure AWS account with credentials
Create a Telegram bot and save the token and chat id for later use of the API
To investigate the Chat ID, you can use your token to get Telegram updates.

Send a text message of your choice to your bot in the Telegram application. After one message in you chat history, you’ll receive your chat ID

Then, refresh your browser.
Identify the numerical chat ID by finding the ID inside the chat JSON object. In the example below, the chat ID is “123456789”

{
    "ok": true,
    "result": [
        {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
         ....
                },
                "chat": {
                    "id": 123456789,
          ....
                },
       ....
            }
        }
    ]
}
Let’s Get Started
Here’s how to get started creating your own generative AI bot:

Check out the template code from the following Sample GitHub repository.
Create an .env file in the root directory of your project with the secrets you created earlier.
This file should contain the following variables:

OPENAI_API_KEY: Your OpenAI API key.

TELEGRAM_BOT_TOKEN: Your Telegram bot token.

TELEGRAM_CHAT_ID: The chat ID of your Telegram channel.

Please note that the .env file should not be committed to your version control system, as it contains sensitive information.
Diving into the CDK Code
In the following “GenaiServerlessStack” stack, we instantiate two Lambda functions: one dedicated to managing client questions and another responsible for configuring the Telegram webhook.

We then complete the following steps:

Establish a Telegram webhook to facilitate the transmission of messages from the Telegram client to our Lambda function URL using a custom resource.
Generate a role endowed with invoke permissions tailored for the custom resource.
Construct a Layer encompassing essential dependencies and integrate it seamlessly with the Lambda functions.
# genai_serverless_stack.py

import json
import os
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    Duration, custom_resources as cr, aws_iam as iam
)

from constructs import Construct
from dotenv import load_dotenv

load_dotenv()


class GenaiServerlessStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.layer = _lambda.LayerVersion(
            self, 'MyLambdaLayer',
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
            code=_lambda.Code.from_asset('genai_serverless/layer'),
            description='LLM Layer includes libs for using llm logic'
        )

        # Define Lambda function for handling chat
        self.chat_handler = self.create_lambda_function(
            'MyLambdaFunction',
            'lambda_handler.handler',
            ['OPENAI_API_KEY', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'],
            Duration.minutes(3)
        )
        fn_url = self.chat_handler.add_function_url(auth_type=_lambda.FunctionUrlAuthType.NONE)

        # Define Lambda function for setting the Telegram webhook
        self.set_webhook_function = self.create_lambda_function(
            'SetWebhookFunction',
            'set_telegram_webhook.handler',
            ['TELEGRAM_TOKEN'],
            Duration.seconds(30)
        )

        # Create IAM role for Lambda function
        role = self.create_lambda_role(self.set_webhook_function)

        # Add the custom resource
        cr.AwsCustomResource(
            self, 'SetWebhook',
            on_create={
                'service': 'Lambda',
                'action': 'invoke',
                'parameters': {
                    'FunctionName': self.set_webhook_function.function_name,
                    'Payload': json.dumps({
                        'ResourceProperties': {
                            'FunctionUrl': fn_url.url
                        }
                    })
                },
                'physical_resource_id': cr.PhysicalResourceId.of('SetWebhook')
            },
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            role=role
        )

    def create_lambda_function(self, function_id, handler, environment_variables, timeout):
        return _lambda.Function(
            self,
            function_id,
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler=handler,
            code=_lambda.Code.from_asset('genai_serverless/lambda'),
            environment={env: os.environ.get(env) for env in environment_variables},
            timeout=timeout,
            layers=[self.layer]
        )

    def create_lambda_role(self, lambda_function):
        role = iam.Role(
            self,
            'CustomResourceRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com')
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=['lambda:InvokeFunction'],
                resources=[lambda_function.function_arn]
            )
        )
        return role
Using Lambda Layer
AWS Lambda enforces a strict 50 MB deployment limit for zipped packages. This constraint includes both your function code and its dependencies (e.g., libraries, frameworks, etc). Exceeding this limit leads to deployment issues. Lambda Layers allow you to separate your core function logic from dependencies. By creating a Lambda Layer, you keep your function code lightweight while moving larger dependencies (such as AI frameworks like LangChain) into the layer. Lambda Layers provide up to 250 MB of storage space, making it an ideal solution for managing substantial dependencies.

With Lambda Layers, your core function code remains small, and only necessary dependencies load at runtime. It also enables dependency reuse across multiple Lambda functions within the same AWS account.

Implementing Lambda Functions Code
Our Lambda Function handler catches the webhook event and extracts the question from the schema. It is important to note that we are saving the memory conversation in the Lambda context while the Lambda is running to make the conversation with the chatbot more engaging and to maintain a history of the conversation. Each Lambda works with only one channel to avoid confusion between conversations. Finally, the Lambda asks the LLM about the question and responds to the user by sending a message to the Telegram channel using the Telegram API.

# lambda_handler.py

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
# set_telegram_webhook.py

import os
import requests


def handler(event, context):
    try:
        function_url = event['ResourceProperties']['FunctionUrl']
        telegram_token = os.environ.get("TELEGRAM_TOKEN")
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
Deployment
To deploy your stack:

Create a virtual environment and install the development requirements using the following command:
pip install -r requirements-dev.txt

Configure your AWS credentials and set up the .env file with your secrets.
Run the deploy.py file from your project directory:
This will install the dependencies required for the layer and deploy your. stack with all the resources.
After a successful deployment, you can access the stack resources inside the CloudFormation service.
AWS Cloudformation stack resources view
Running “deploy.py” and then run cdk synth and deploy and the resource created.
Introducing Our New Digital Friend
Your Serverless application bot is now up and running! You can test it out by asking questions in your Telegram channel and receiving answers from the AI model. I hope you found our dive into a GenAI application, using serverless technology in parallel with third-party frameworks such as LangChain, enlightening and that it this has piqued your interest in exploring the creation of your own custom chatbot app.

chat with ai bot in telegram conversation