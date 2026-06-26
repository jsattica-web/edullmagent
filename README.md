# Edu LLM Agent

Educational materials and examples for building LLM agents, tool-calling flows,
MCP servers, skills, retrieval workflows, and related notebook exercises.

## Contents

- `*.ipynb` - lesson notebooks and answer notebooks.
- `edu_agent/` - additional agent workflow notebooks.
- `skills/` - example skill definitions and supporting scripts/data.
- `weather_reports/` - generated report examples.
- `*_server.py`, `tools.py`, `build_agent.py` - Python examples for tools,
  MCP, and agent execution.

## Setup

Create a local virtual environment and install dependencies:

```powershell
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

## Environment Variables

Do not commit real secrets. Copy `.env.example` to `.env` locally and fill in
only the values you need:

```powershell
Copy-Item .env.example .env
```

The project may use these variables depending on the notebook or script:

- `OPENAI_API_KEY`
- `PINECONE_API_KEY`
- `SLACK_APP_TOKEN`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNEL_ID`
- `TAVILY_API_KEY`
- `UPSTAGE_API_KEY`

For GitHub Actions or hosted environments, store these values as repository or
environment secrets instead of committing `.env`.

## Notes

Notebook outputs and local databases are included where they are part of the
class material. Local runtime folders such as `.venv/`, `__pycache__/`, and
`.ipynb_checkpoints/` are ignored.
