#!/usr/bin/env bash
# One command to start Company OS the right way (GUI + GPU LLM server ensured).
cd "$(dirname "$0")"

# 1) GPU LLM server (native ollama on port 11435)
bash start_gpu_ollama.sh

# 2) make sure a fast routing model exists (only downloads if missing)
export PATH="$HOME/.local/bin:$PATH"
if ! ollama list | grep -q llama3.2:1b; then
  echo "Pulling llama3.2:1b ..."
  ollama pull llama3.2:1b
fi

# 3) launch the desktop app
source venv/bin/activate
python main.py
