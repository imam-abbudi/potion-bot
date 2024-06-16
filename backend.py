import threading
import asyncio
import json
import requests
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import websockets

app = Flask(__name__)
socketio = SocketIO(app)

API_KEY = "e502cd93180ba88db3f55242a66a6db8f690"
WATCHED_ACCOUNTS = {}
USERS = {}
PROCESSED_EVENTS = set()  # To keep track of processed event IDs

def start_watching(account_name):
    url = "https://twitter-api.axsys.us/v1/watched"
    headers = {
        "Authorization": API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    data = {"handle": account_name}
    response = requests.post(url, headers=headers, json=data)
    print(f"Response: {response.status_code} - {response.text}")
    return response.status_code == 200

@app.route('/watch', methods=['POST'])
def watch():
    data = request.json
    username = data.get('user_id')
    account_name = data.get('account_name')
    if not username or not account_name:
        return jsonify({"message": "user_id and account_name are required"}), 400
    if start_watching(account_name):
        WATCHED_ACCOUNTS[account_name] = username
        print(f"{username} started watching {account_name}")
        return jsonify({"message": "success"}), 200
    return jsonify({"message": "failed"}), 400

@socketio.on('connect')
def handle_connect():
    username = request.headers.get('username')
    print(f"Client connected with username: {username}")
    if username:
        USERS[username] = request.sid
        emit('connected', {'user_id': username})

@socketio.on('disconnect')
def handle_disconnect():
    username = request.headers.get('username')
    print(f"Client disconnected with username: {username}")
    if username in USERS:
        del USERS[username]

def handle_event(event):
    event_id = event.get('tweet', {}).get('id')
    if event_id in PROCESSED_EVENTS:
        return  # Skip already processed events
    PROCESSED_EVENTS.add(event_id)

    account_name = event.get('tweet', {}).get('author', {}).get('handle')
    username = WATCHED_ACCOUNTS.get(account_name)
    if username:
        if username in USERS:
            socketio.emit('event', {'user_id': username, 'event': event}, to=USERS[username])
        else:
            print(f"Error: {username} not found in USERS dictionary")

async def fetch_events():
    uri = f"wss://etw-api.axsys.us/v1/events?authorization={API_KEY}"
    async with websockets.connect(uri) as websocket:
        while True:
            try:
                message = await websocket.recv()
                if message == 'PING':
                    await websocket.send('PONG')
                    continue
                event = json.loads(message)
                print(f"Received message from websocket: {message}")
                handle_event(event)
            except websockets.ConnectionClosed:
                print("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(1)
                await fetch_events()
            except json.JSONDecodeError:
                print(f"Failed to decode JSON: {message}")

def start_event_listener():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_events())

if __name__ == '__main__':
    threading.Thread(target=start_event_listener).start()
    socketio.run(app, host='0.0.0.0', port=8000)
