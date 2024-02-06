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
