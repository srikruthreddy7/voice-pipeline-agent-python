<a href="https://livekit.io/">
  <img src="./.github/assets/livekit-mark.png" alt="LiveKit logo" width="100" height="100">
</a>

# Python Voice Agent

<p>
  <a href="https://cloud.livekit.io/projects/p_/sandbox"><strong>Deploy a sandbox app</strong></a>
  •
  <a href="https://docs.livekit.io/agents/overview/">LiveKit Agents Docs</a>
  •
  <a href="https://livekit.io/cloud">LiveKit Cloud</a>
  •
  <a href="https://blog.livekit.io/">Blog</a>
</p>

A basic example of a voice agent using LiveKit and Python.

## Dev Setup

Clone the repository and install dependencies to a virtual environment:

```console
# Linux/macOS
cd voice-pipeline-agent-python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 agent.py download-files
```

<details>
  <summary>Windows instructions (click to expand)</summary>
  
```cmd
:: Windows (CMD/PowerShell)
cd voice-pipeline-agent-python
python3 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
</details>


Set up the environment by copying `.env.example` to `.env.local` and filling in the required values:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `OPENAI_API_KEY`
- `CARTESIA_API_KEY`
- `DEEPGRAM_API_KEY`

You can also do this automatically using the LiveKit CLI:

```console
lk app env
```

Run the agent:

```console
python3 agent.py dev
```

This agent requires a frontend application to communicate with. You can use one of our example frontends in [livekit-examples](https://github.com/livekit-examples/), create your own following one of our [client quickstarts](https://docs.livekit.io/realtime/quickstarts/), or test instantly against one of our hosted [Sandbox](https://cloud.livekit.io/projects/p_/sandbox) frontends.

# LiveKit Agent Dispatcher API

This is a FastAPI application that dispatches LiveKit voice agents to rooms when requests come in.

## Setup

1. Copy `.env.local.example` to `.env.local` and fill in your LiveKit credentials:
   ```
   cp .env.local.example .env.local
   ```

2. Edit `.env.local` with your actual LiveKit API key and secret:
   ```
   LIVEKIT_API_KEY=your_api_key
   LIVEKIT_API_SECRET=your_api_secret
   LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the API Server

Start the FastAPI server:

```
python app.py
```

Or run with uvicorn directly:

```
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Create a LiveKit Agent Dispatch (Asynchronous)

```
POST /dispatch/
```

Body:
```json
{
  "room_name": "my-room",
  "agent_name": "test-agent",
  "metadata": "optional metadata"
}
```

This endpoint will dispatch the agent asynchronously and return immediately.

### Create a LiveKit Agent Dispatch (Synchronous)

```
POST /dispatch-sync/
```

Body:
```json
{
  "room_name": "my-room",
  "agent_name": "test-agent",
  "metadata": "optional metadata"
}
```

This endpoint will wait for the dispatch to be created before returning.

## Interactive API Documentation

FastAPI provides automatic interactive API documentation:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing with cURL

```bash
curl -X POST http://localhost:8000/dispatch/ \
  -H "Content-Type: application/json" \
  -d '{"room_name": "my-room", "agent_name": "test-agent"}'
```
