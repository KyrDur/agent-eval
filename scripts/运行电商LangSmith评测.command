#!/bin/zsh
set -e
task_repo="$(cd "$(dirname "$0")/.." && pwd)"
task_python="${AGENTEVAL_PYTHON:-}"
if [[ -z "$task_python" ]]; then
  for candidate in "$task_repo/AgentEval/.venv/bin/python"; do
    if [[ -x "$candidate" ]]; then task_python="$candidate"; break; fi
  done
fi
if [[ -z "$task_python" ]]; then
  print '请先安装 requirements-langsmith.txt，并设置 AGENTEVAL_PYTHON 指向 Python 3.12。'
  exit 1
fi
"$task_python" -u "$task_repo/scripts/langsmith-eval.py" "$@"
if [[ -t 0 ]]; then
  print '评测完成。上方有 LangSmith 实验链接。按回车关闭窗口。'
  read -r task_done
fi
