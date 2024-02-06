#!/usr/bin/env python
import argparse
import os
import sys

PLATFORMS = "manylinux2014_x86_64"
LAYER_REQUIREMENTS_FILE = "requirements-layer.txt"
LAYER_DEPENDENCIES_FOLDER = "genai_serverless/layer/python"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-approval', default='broadening')
    parser.add_argument('--synth', nargs='?', const=True, help='Synthesize cloudformation.yml before deploying')
    args = parser.parse_args()
    build_layer(args)
    deploy_cdk(args)


def build_layer(args):
    print('Building the lambda package...')
    # Check if the layer folder and the python subfolder exist
    if not os.path.exists(LAYER_DEPENDENCIES_FOLDER):
        # If not, create them
        os.makedirs(LAYER_DEPENDENCIES_FOLDER)
    if return_code := os.system(
            f'pip install --platform={PLATFORMS} --only-binary=:all: -r {LAYER_REQUIREMENTS_FILE} -t {LAYER_DEPENDENCIES_FOLDER}'):
        print(f'build layer failed with return code: {return_code}')
        sys.exit(1)


def deploy_cdk(args) -> None:
    print('cdk deploy...')
    if return_code := os.system(f'cdk deploy --require-approval {args.require_approval}'):
        print(f'cdk deploy failed with return code: {return_code}')
        sys.exit(1)


if __name__ == '__main__':
    main()
