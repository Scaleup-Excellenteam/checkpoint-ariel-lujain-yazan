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

test('a security block is visible and is not added as a successful chat message', () => {
  const socket = login();
  act(() => socket.receive({ type: 'ROOMS_LIST', rooms: [{ id: 7, name: 'Study' }] }));
  fireEvent.click(screen.getByRole('button', { name: 'Join Room' }));
  act(() => socket.receive({ type: 'JOIN_ROOM_RESULT', success: true, room_id: 7 }));

  fireEvent.change(screen.getByPlaceholderText('Write a message...'), {
    target: { value: 'message that will be blocked' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  act(() => socket.receive({
    type: 'SECURITY_FEEDBACK',
    action: 'BLOCK',
    reason: 'SENSITIVE_CONTENT',
    message: 'The message was not sent because it may contain sensitive information.',
    room_id: 7,
  }));

  expect(screen.getByText('Action blocked')).toBeTruthy();
  expect(screen.getByText('Reason: SENSITIVE_CONTENT')).toBeTruthy();
  expect(screen.queryByText('message that will be blocked')).toBeNull();
});

test('a spam-disconnect keeps the block reason visible on the login screen', () => {
  const socket = login();

  act(() => {
    socket.receive({
      type: 'SECURITY_FEEDBACK',
      action: 'BLOCK',
      reason: 'SPAM_DETECTED',
      message: 'The action was blocked because spam-like activity was detected.',
      room_id: 7,
    });
    socket.receive({ type: 'DISCONNECTED' });
  });

  expect(screen.getByText('Welcome to the Chat')).toBeTruthy();
  expect(screen.getByText('Action blocked')).toBeTruthy();
  expect(screen.getByText('Reason: SPAM_DETECTED')).toBeTruthy();
});

test('technical errors remain errors and are not labeled as security blocks', () => {
  const socket = login();

  act(() => {
    socket.receive({
      type: 'SECURITY_FEEDBACK',
      action: 'BLOCK',
      reason: 'INVALID_INPUT',
      message: 'The action was blocked because the submitted data is invalid.',
    });
    socket.receive({ type: 'ERROR', reason: 'Bridge unavailable' });
  });

  expect(screen.getByText('Bridge unavailable')).toBeTruthy();
  expect(screen.queryByText('Action blocked')).toBeNull();
});

test('login rate-limit feedback shows retry information without enforcing a timer', () => {
  render(<WebSocketProvider><App /></WebSocketProvider>);
  const socket = Socket.instances.at(-1);
  act(() => { socket.onopen(); socket.receive({ type: 'CONNECTED' }); });

  act(() => socket.receive({
    type: 'SECURITY_FEEDBACK',
    action: 'BLOCK',
    reason: 'LOGIN_RATE_LIMITED',
    message: 'Too many login attempts. Please wait before trying again.',
    retry_after_seconds: 45,
  }));

  expect(screen.getByText('Reason: LOGIN_RATE_LIMITED')).toBeTruthy();
  expect(screen.getByText('Try again in 45 seconds.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Login' }).disabled).toBe(false);
});

test('URL reputation outages use the safe generic security message', () => {
  render(<WebSocketProvider><App /></WebSocketProvider>);
  const socket = Socket.instances.at(-1);
  act(() => { socket.onopen(); socket.receive({ type: 'CONNECTED' }); });

  act(() => socket.receive({
    type: 'SECURITY_FEEDBACK',
    action: 'BLOCK',
    reason: 'SECURITY_CHECK_UNAVAILABLE',
    message: 'The action could not be completed because a security check is unavailable.',
  }));

  expect(screen.getByText('Action blocked')).toBeTruthy();
  expect(screen.getByText('Reason: SECURITY_CHECK_UNAVAILABLE')).toBeTruthy();
  expect(screen.getByText('The action could not be completed because a security check is unavailable.')).toBeTruthy();
  expect(screen.queryByText(/VIRUSTOTAL_API_KEY/)).toBeNull();
});

test('normal messages keep the existing room behavior', () => {
  const socket = login();
  act(() => socket.receive({ type: 'ROOMS_LIST', rooms: [{ id: 7, name: 'Study' }] }));
  fireEvent.click(screen.getByRole('button', { name: 'Join Room' }));
  act(() => {
    socket.receive({ type: 'JOIN_ROOM_RESULT', success: true, room_id: 7 });
    socket.receive({ type: 'MESSAGE_RECEIVED', room_id: 7, sender: 'alice', text: 'hello' });
  });

  expect(screen.getByText('hello')).toBeTruthy();
  expect(screen.queryByText('Action blocked')).toBeNull();
});

test('an ordinary login failure remains a technical login error', () => {
  render(<WebSocketProvider><App /></WebSocketProvider>);
  const socket = Socket.instances.at(-1);
  act(() => { socket.onopen(); socket.receive({ type: 'CONNECTED' }); });
  fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'wrong' } });
  fireEvent.click(screen.getByRole('button', { name: 'Login' }));

  act(() => socket.receive({
    type: 'LOGIN_RESULT',
    success: false,
    reason: 'Invalid username or password',
  }));

  expect(screen.getByText('Invalid username or password')).toBeTruthy();
  expect(screen.queryByText('Action blocked')).toBeNull();
});
