# Testing Guide

This document explains how to run the Client Backend tests.

## 1. Go to the project directory

```bash
cd ~/checkPoint_project/checkpoint-ariel-lujain-yazan
```

## 2. Activate the virtual environment

```bash
source .venv/bin/activate
```

## 3. Configure the server address

The Client Backend receives the server address from the `CHAT_SERVER_URL` environment variable.

For the current development environment, Yazan's server is running at:

```bash
export CHAT_SERVER_URL="ws://172.20.10.3:8000/"
```

If Yazan's IP address changes, update only this environment variable.

The Python source code does not need to be changed.

To check Yazan's current IP address, run on Yazan's computer:

```bash
hostname -I
```

## 4. Install test dependencies

If the testing dependencies are not installed yet:

```bash
python -m pip install pytest httpx
```

## 5. Run the Client Backend tests

```bash
python -m pytest -v \
  tests/test_client_auth.py \
  tests/test_client_rooms.py \
  tests/test_bridge.py
```

## Test Files

### `tests/test_client_auth.py`

Tests authentication and Client security behavior, including:

* Signup requests
* Login requests
* JWT storage
* Invalid JWT handling
* Clearing a token after failed login
* Logout behavior
* Authenticated JSON requests
* Invalid JSON request types
* Duplicate connections
* WebSocket connection security limits

### `tests/test_client_rooms.py`

Tests authenticated room operations, including:

* Listing rooms
* Creating rooms
* Joining rooms
* Leaving rooms
* Sending room messages
* Authentication requirements
* Room ID validation
* Room name validation
* Message length validation
* JWT attachment to protected requests

### `tests/test_bridge.py`

Tests the local FastAPI Bridge, including:

* WebSocket connection from the UI
* Origin validation
* Login forwarding
* Preventing JWT exposure to the UI
* Username validation
* Room request forwarding
* Room ID validation
* Message forwarding
* Logout handling
* Unknown request handling

## Current Test Result

The current Client Backend test suite contains:

```text
48 tests
```

The latest successful run:

```text
48 passed
0 failed
```

Warnings produced by third-party FastAPI / Starlette / HTTPX dependencies do not represent failed tests.

## Important

These tests verify the Client Backend independently from the real UI and Server.

They do not replace the final integration test.

After the UI, Client Backend, and Server are connected, the full system should also be tested using:

```text
Browser UI
    ↓
FastAPI Bridge
    ↓
ChatClient
    ↓
WebSocket
    ↓
Server
```
