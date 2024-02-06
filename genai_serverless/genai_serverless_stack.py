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

        # Create the Lambda function
        self.chat_handler = _lambda.Function(
            self, 'MyLambdaFunction',
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler='lambda_handler.handler',
            code=_lambda.Code.from_asset('genai_serverless/lambda'),
            environment={
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
                "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_TOKEN"),
                "TELEGRAM_CHAT_ID": os.environ.get("TELEGRAM_CHAT_ID")
            },
            timeout=Duration.minutes(3),
            layers=[self.layer]
        )
        fn_url = self.chat_handler.add_function_url(auth_type=_lambda.FunctionUrlAuthType.NONE)

        # Create the Lambda function for setting the Telegram webhook
        set_webhook_function = _lambda.Function(
            self, 'SetWebhookFunction',
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler='set_telegram_webhook.handler',
            code=_lambda.Code.from_asset('genai_serverless/lambda'),
            environment={
                "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_TOKEN"),
            },
            layers=[self.layer],
            timeout=Duration.seconds(30),
        )
        # Create an IAM role with the necessary permissions
        role = iam.Role(
            self, 'CustomResourceRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com')
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=['lambda:InvokeFunction'],
                resources=[set_webhook_function.function_arn]
            )
        )
        # Add the custom resource
        cr.AwsCustomResource(
            self, 'SetWebhook',
            on_create={
                'service': 'Lambda',
                'action': 'invoke',
                'parameters': {
                    'FunctionName': set_webhook_function.function_name,
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
