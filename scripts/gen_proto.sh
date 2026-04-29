#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

uv run python -m grpc_tools.protoc \
    --proto_path=app/grpc \
    --python_out=app/grpc/generated \
    --grpc_python_out=app/grpc/generated \
    app/grpc/gateway.proto

sed -i 's/^import gateway_pb2/from app.grpc.generated import gateway_pb2/' \
    app/grpc/generated/gateway_pb2_grpc.py

echo "Proto generation complete."
