from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket


# def test_websocket(api_client):
#     with api_client.websocket_connect("/api/ws") as websocket:
#         websocket: WebSocket
#         data_1 = websocket.receive_json()
#         data_2 = websocket.receive_json()

#     assert data_1 == {"target": "user", "message": "update"}
#     assert data_2 == {"target": "ticker", "message": "update"}
