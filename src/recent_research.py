def remember_stock(history, code, name, limit=8):
    """Return session-only browsing history; never persist personal research."""
    code = str(code).strip().zfill(6)
    if len(code) != 6 or not code.isdigit():
        return list(history or [])
    entries = [{'code': code, 'name': str(name).strip()}]
    seen = {code}
    for item in history or []:
        if not isinstance(item, dict) or item.get('code') in seen:
            continue
        if not item.get('code'):
            continue
        entries.append(dict(item))
        seen.add(item['code'])
    return entries[:limit]
