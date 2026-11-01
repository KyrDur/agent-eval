"""Only the development pack is served before study lock; holdout stays server-side."""
import json
from pathlib import Path

def public_pack():
    return json.loads((Path(__file__).parent/'data/rag-policy-v1/public-pack.json').read_text())
