# Building a Serverless LangChain-Powered Telegram Q&A Bot: A Step-by-Step Guide

# Introduction

In this blog post, I will walk you through the process of creating your own LangChain-based Telegram bot. LangChain is a ***framework for developing applications powered by language models***. I will share some personal insights along the way.
I will present a template for creating a serverless application using AWS CDK and LangChain.
The template can be used in its entirety or in parts. Additionally, we have introduced a private Telegram channel that can be used to ask questions and receive answers from an AI model customized to suit your needs.

## **Create a serverless application using AWS CDK as IaC**

Our primary focus in this post is on the implementation of a serverless application using AWS CDK as infrastructure as code, rather than the design or handling all security issues.

![langchain-blog.drawio.png](Building%20a%20Serverless%20LangChain-Powered%20Telegram%20Q%20948a3b5a345844ca8ecd84f802e2ecb0/langchain-blog.drawio.png)

# Prerequisites

- An [Aws account](https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-creating.html)
- The AWS CDK Toolkit (for this blog, I used version 2.118.0). More information can be found [here](https://docs.aws.amazon.com/cdk/v2/guide/cli.html)
- [Python 3.11 or above](https://www.python.org/downloads/)
- Create an OpenAI API key [here](https://platform.openai.com/api-keys).
- Configure AWS account with credentials. [For more information on how to configure your AWS account, please refer to the official Amazon documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).
- Create a Telegram bot and save the token and chat id for later use of the API. [You can learn how to create a Telegram bot and get its token by following the instructions provided on this page](https://sendpulse.com/knowledge-base/chatbot/telegram/create-telegram-chatbot).
    - To investigate the chat id, you can use your token and surf in the browser to
        
        ```python
        https://api.telegram.org/bot<API-access-token>/getUpdates?offset=0
        ```
        
    - Send a message to your bot in the Telegram application. The message text can be anything. Your chat history must include at least one message to get your chat ID.
    - Refresh your browser.
    - Identify the numerical chat ID by finding the `id` inside the `chat` JSON object. In the example below, the chat ID is `123456789`.
        
        
        ```jsx
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
        ```
        

# Challenges

In order to overcome the 50MB hard limit for zipped Lambda deployment, we are using Lambda Layer to separate the core function logic from dependencies. This allows us to use LangChain, which is currently over 50MB, as the AI framework for our serverless application. Lambda Layer can accommodate a maximum of 250MB for your package, making it an ideal solution for our needs. Additionally, using layers allows us to share dependencies across multiple functions, making our application more efficient and scalable.

[https://giphy.com/embed/B5d9Sezw8rEHNxsc46](https://giphy.com/embed/B5d9Sezw8rEHNxsc46)

## Let’s Get started

Here are the steps to create your own generative ai bot:

- Check out the template code from the following  [Gihub repository](https://github.com/DanBeladev/GenAIServerless).
- Create an **`.env`** file in the root directory of your project with the secrets you created earlier. This file should contain the following variables:
    - **`OPENAI_API_KEY`**: Your OpenAI API key.
    - **`TELEGRAM_BOT_TOKEN`**: Your Telegram bot token.
    - **`TELEGRAM_CHAT_ID`**: The chat ID of your Telegram channel.
    
    Please note that the **`.env`** file should not be committed to your version control system, as it contains sensitive information.
    

## Dive in to the CDK code

In the following “GenaiServerlessStack” stack, we instantiate two Lambda functions: one dedicated to managing client questions and another responsible for configuring the Telegram webhook.

Utilizing a custom resource, we establish a Telegram webhook to facilitate the transmission of messages from the Telegram client to our Lambda function URL. Concurrently, we generate a role endowed with invoke permissions tailored for the custom resource.

Furthermore, we construct a Layer encompassing essential dependencies and integrate it seamlessly with the Lambda functions.

**genai_serverless_stack.py**

```python
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
                            'FunctionUrl': self.chat_handler.add_function_url(
                                auth_type=_lambda.FunctionUrlAuthType.NONE).url
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
```

## Lambda functions code

Our Lambda Function handler will catch the webhook event and extract the question from the schema. It is important to note that we are saving the memory conversation in the Lambda context while the Lambda is running to make the conversation with the chatbot more engaging and to maintain a history of the conversation. Each Lambda can work with only one channel to avoid confusion between conversations. Finally, the Lambda will ask the LLM about the question and respond to the user by sending a message to the Telegram channel using the Telegram API.

**lambda_handler.py**

```python
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
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
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
```

**set_telegram_webhook.py**

```python
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
```

# Deployment

To deploy your stack, follow these steps:

1. Create a virtual environment and install the development requirements using the following command:

> pip install -r requirements-dev.txt
> 
1.  Configure your AWS credentials and set up the **`.env`** file with your secrets.
2. Run the **`deploy.py`** file from your project directory:
    
    This will install the dependencies required for the layer and deploy your stack with all the resources.
    
3. After a successful deployment, you can access the stack resources inside the CloudFormation service.

![Untitled](Building%20a%20Serverless%20LangChain-Powered%20Telegram%20Q%20948a3b5a345844ca8ecd84f802e2ecb0/Untitled.png)

![cdk-deploy.drawio.png](Building%20a%20Serverless%20LangChain-Powered%20Telegram%20Q%20948a3b5a345844ca8ecd84f802e2ecb0/cdk-deploy.drawio.png)

# Final result

Your serverless application bot is now up and running! You can test it out by asking questions in your Telegram channel and receiving answers from the AI model.

![Untitled](Building%20a%20Serverless%20LangChain-Powered%20Telegram%20Q%20948a3b5a345844ca8ecd84f802e2ecb0/Untitled%201.png)