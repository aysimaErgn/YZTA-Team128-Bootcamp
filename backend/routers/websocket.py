from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict

router = APIRouter(tags=["websocket"])

class ConnectionManager:
    def __init__(self):
        # elder_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, elder_id: str):
        await websocket.accept()
        self.active_connections[elder_id] = websocket
        print(f"[WS] {elder_id} bağlandı.")

    def disconnect(self, elder_id: str):
        if elder_id in self.active_connections:
            del self.active_connections[elder_id]
            print(f"[WS] {elder_id} bağlantısı koptu.")

    async def send_personal_message(self, message: dict, elder_id: str):
        websocket = self.active_connections.get(elder_id)
        if websocket:
            try:
                await websocket.send_json(message)
                print(f"[WS] {elder_id} cihazına mesaj gönderildi: {message}")
            except Exception as e:
                print(f"[WS] {elder_id} cihazına mesaj gönderilemedi: {e}")
                self.disconnect(elder_id)

manager = ConnectionManager()

@router.websocket("/ws/medication/{elder_id}")
async def websocket_endpoint(websocket: WebSocket, elder_id: str):
    await manager.connect(websocket, elder_id)
    try:
        while True:
            # Sadece bağlantıyı açık tutmak için bekle
            data = await websocket.receive_text()
            print(f"[WS] {elder_id} mesaj gönderdi: {data}")
    except WebSocketDisconnect:
        manager.disconnect(elder_id)
