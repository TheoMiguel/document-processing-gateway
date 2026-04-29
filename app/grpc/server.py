import grpc
import grpc.aio
from grpc_reflection.v1alpha import reflection

from app.core.events import EventPublisher
from app.core.orchestrator import PipelineOrchestrator
from app.grpc.generated import gateway_pb2, gateway_pb2_grpc
from app.grpc.servicer import DocumentGatewayServicer

GRPC_PORT = 50051


async def create_grpc_server(
    publisher: EventPublisher,
    orchestrator: PipelineOrchestrator,
) -> grpc.aio.Server:
    server = grpc.aio.server()
    servicer = DocumentGatewayServicer(publisher=publisher, orchestrator=orchestrator)
    gateway_pb2_grpc.add_DocumentGatewayServicer_to_server(servicer, server)
    reflection.enable_server_reflection(
        (
            gateway_pb2.DESCRIPTOR.services_by_name["DocumentGateway"].full_name,
            reflection.SERVICE_NAME,
        ),
        server,
    )
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    return server
