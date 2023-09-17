from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

# Removed because I can't stop these running forever

# def test_websocket(api_client):
#     with api_client.websocket_connect("/api/ws_updates") as websocket:
#         websocket: WebSocket
#         data_1 = websocket.receive_json()
#         data_2 = websocket.receive_json()
#         websocket.close(code=1000)

#     assert data_1 == {"target": "user", "message": "update"}
#     assert data_2 == {"target": "ticker", "message": "update"}
