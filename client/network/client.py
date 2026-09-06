from threading import Thread

from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed


SERVER_URL = "ws://172.20.10.5:8000"


def receive_messages(websocket):
    try:
        while True:
            message = websocket.recv()
            print(f"\nMessage: {message}")
    except ConnectionClosed:
        print("\nDisconnected from server.")


with connect(SERVER_URL) as websocket:
    print("Connected to the server.")

    receiver = Thread(
        target=receive_messages,
        args=(websocket,),
        daemon=True,
    )
    receiver.start()

    while True:
        message = input("You: ")

        if message == "/exit":
            break

        websocket.send(message)