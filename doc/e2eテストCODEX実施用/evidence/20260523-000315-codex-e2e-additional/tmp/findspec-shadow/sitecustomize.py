import importlib.util as _util
_real_find_spec = _util.find_spec
def _patched_find_spec(name, *args, **kwargs):
    if name in {"FlagEmbedding", "qdrant_client"}:
        return None
    return _real_find_spec(name, *args, **kwargs)
_util.find_spec = _patched_find_spec
