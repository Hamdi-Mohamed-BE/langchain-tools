# Mobile App (Expo + React Native)

This folder contains a React Native client for the AI Gym Coach backend.

## What It Uses

- Expo + React Native + TypeScript
- Expo SDK 54 (compatible with latest Expo Go)
- Node.js 20.19.4 or newer
- WebSocket chat endpoint: `GET ws://<host>:8000/chat/ws`
- Existing backend AI/tool pipeline through `ChatService.stream_message(...)`

## Features Included

- Email/password signup page
- Email/password login page
- Auth session persistence with AsyncStorage
- Connect/disconnect to backend WebSocket chat
- Send messages with `user_id`
- Stream assistant response token-by-token
- Render tool events (`type: tool`)
- Display usage events (`type: usage`)
- Load existing chat history over HTTP

## Auth Flow

Backend endpoints used:
- `POST /auth/register`
- `POST /auth/login`

Request payload:

```json
{
  "email": "user@example.com",
  "password": "strongpass123"
}
```

Response payload:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user_id": 1
}
```

In mobile app:
- Auth screen toggles between `Login` and `Sign Up` pages.
- Successful auth stores session locally and switches to chat page.
- Chat page uses authenticated `user_id` automatically.
- Logout clears local session and returns to auth screen.

## Message Protocol

Client -> Server (JSON text frame):

```json
{
  "user_id": 1,
  "message": "build me a 4 day hypertrophy plan"
}
```

Server -> Client events (`WebSocket.send_json`):

- `{ "type": "status", "text": "Thinking..." }`
- `{ "type": "tool", "tool": "...", "text": "..." }`
- `{ "type": "usage", ... }`
- `{ "type": "token", "text": "partial token" }`
- `{ "type": "done" }`
- `{ "type": "error", "text": "..." }`

## Setup

1. From the repository root, open `mobile/.env.example` and create `mobile/.env`.
2. Set `EXPO_PUBLIC_API_BASE_URL`.
3. (Optional for YouTube API search utility) Set `EXPO_PUBLIC_YOUTUBE_API_KEY`.

Use one of these values:
- Android emulator: `http://10.0.2.2:8000`
- iOS simulator: `http://127.0.0.1:8000`
- Physical phone: `http://<your-lan-ip>:8000`

For the embedded YouTube preview component used in workout list, install dependencies:

```bash
cd mobile
yarn install
```

## Commands To Run (you run these)

Windows scripts from repository root:

```bat
setup_mobile.bat
run_mobile.bat
```

`setup_mobile.bat` installs dependencies and runs `npx expo install --fix` to align package versions with the configured Expo SDK.

`setup_mobile.bat` installs dependencies and runs local Expo CLI `install --fix` to align package versions with the configured Expo SDK.

Manual commands:

```bash
cd mobile
yarn install
yarn start
```

Then launch target platform:

```bash
yarn android
# or
yarn ios
```

## Backend Notes

- Ensure backend runs on `0.0.0.0` if using a physical device.
- CORS is enabled from backend settings via `cors_allow_origins`.
- WebSocket route is implemented in `app/routers/chat_router.py` at `/chat/ws`.

## WSL + Android Notes

If running Expo from WSL, pressing `a` in Metro may fail with Android SDK/`adb` errors like:
- `Failed to resolve the Android SDK path`
- `Error: spawn adb ENOENT`

Use one of these options:
- Preferred: scan QR code with Expo Go on a physical Android/iOS device.
- Android emulator from Windows host: set `ANDROID_HOME`/`ANDROID_SDK_ROOT` in the shell running Expo and ensure `adb` is on `PATH`.
- If you do not need web, run native-only flow and avoid opening web target.

If you choose to run from WSL, avoid mounting from `/mnt/c/...` when possible because Metro file watching can fail with `EIO`.

## Install Warnings

During `npm install`, you may see deprecation warnings for packages like `glob`, `rimraf`,
`inflight`, or legacy Babel proposal plugins.
During `yarn install`, you may see deprecation warnings for packages like `glob`, `rimraf`,
`inflight`, or legacy Babel proposal plugins.

Current status for this project:
- These are transitive dependencies from React Native / Expo toolchain internals.
- They are not direct dependencies in `mobile/package.json`.
- Your install is valid when it finishes successfully and reports `found 0 vulnerabilities`.
- Avoid forcing `overrides` for these packages unless a tested Expo SDK upgrade requires it.

To run compatibility checks:

```bash
cd mobile
yarn doctor
```

If dependency alignment is needed manually, use local Expo CLI after install:

```bash
cd mobile
yarn install
yarn run expo install --fix
```

## Current App Entry

- Main screen: `mobile/App.tsx`
- WS client: `mobile/src/services/chatSocket.ts`
- URL helpers: `mobile/src/config/env.ts`
- Message type contracts: `mobile/src/types/chat.ts`
