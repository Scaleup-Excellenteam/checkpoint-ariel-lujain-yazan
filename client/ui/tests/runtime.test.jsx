// @vitest-environment jsdom
import React, { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { WebSocketProvider } from '../src/lib/ws';
import App from '../src/App';

class Socket {
  static OPEN = 1;
  static instances = [];
  readyState = 1;
  sent = [];
  constructor() { Socket.instances.push(this); }
  send(raw) { this.sent.push(JSON.parse(raw)); }
  close() { this.readyState = 3; this.onclose?.(); }
  receive(data) { this.onmessage({ data: JSON.stringify(data) }); }
}

beforeEach(() => {
  Socket.instances = [];
  vi.stubGlobal('WebSocket', Socket);
  vi.stubEnv('VITE_USE_MOCKS', 'false');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function login() {
  render(<StrictMode><WebSocketProvider><App /></WebSocketProvider></StrictMode>);
  const socket = Socket.instances.at(-1);
  act(() => { socket.onopen(); socket.receive({ type: 'CONNECTED' }); });
  fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Login' }));
  act(() => socket.receive({ type: 'LOGIN_RESULT', success: true }));
  return socket;
}

test('room responses do not repeat LIST_ROOMS; joining uses the displayed id', () => {
  const socket = login();
  const count = socket.sent.filter(item => item.type === 'LIST_ROOMS').length;
  expect(count).toBeGreaterThan(0);
  act(() => socket.receive({ type: 'ROOMS_LIST', rooms: [{ id: 7, name: 'Study' }] }));
  expect(socket.sent.filter(item => item.type === 'LIST_ROOMS')).toHaveLength(count);
  fireEvent.click(screen.getByRole('button', { name: 'Join Room' }));
  expect(socket.sent.at(-1)).toEqual({ type: 'JOIN_ROOM', room_id: 7 });
});

test('a fresh database supports creating and joining a room', () => {
  const socket = login();
  fireEvent.change(screen.getByRole('textbox', { name: 'Room name' }), { target: { value: 'Study' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Room' }));
  expect(socket.sent.at(-1)).toEqual({ type: 'CREATE_ROOM', name: 'Study' });
  act(() => socket.receive({ type: 'CREATE_ROOM_RESULT', success: true, room: { id: 9, name: 'Study' } }));
  fireEvent.click(screen.getByRole('button', { name: 'Join Room' }));
  expect(socket.sent.at(-1).room_id).toBe(9);
});

test('logout leaves the browser connection usable for the next login', () => {
  const socket = login();
  fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
  act(() => {
    socket.receive({ type: 'DISCONNECTED' });
    socket.receive({ type: 'LOGOUT_RESULT', success: true });
  });
  fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Login' }));
  expect(socket.sent.at(-1).type).toBe('LOGIN');
  act(() => { socket.receive({ type: 'CONNECTED' }); socket.receive({ type: 'LOGIN_RESULT', success: true }); });
  expect(screen.getByText('Dashboard')).toBeTruthy();
});
