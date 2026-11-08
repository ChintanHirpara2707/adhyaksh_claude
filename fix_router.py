import io
p = 'adhyaksh/chat/router.py'
s = io.open(p, encoding='utf-8').read()
old = '''    m = re.search(r"\\bopen\\s+([\\w][\\w\\s]*?)[\\s?.!]*$", t, re.IGNORECASE)
    if m:
        app = find_app(t)
        if app:
            return Rule("app_open", {"app": app})
    m = _SPECIAL_FOLDER.match(t)
    if m:
        return Rule("special_folder_open", {"folder": m.group(1)})
    rule = parse_web_command(t)
    if rule:
        return rule'''
new = '''    rule = parse_web_command(t)
    if rule:
        return rule
    m = _SPECIAL_FOLDER.match(t)
    if m:
        return Rule("special_folder_open", {"folder": m.group(1)})
    m = re.search(r"\\bopen\\s+([\\w][\\w\\s]*?)[\\s?.!]*$", t, re.IGNORECASE)
    if m:
        app = find_app(t)
        if app:
            return Rule("app_open", {"app": app})'''
assert old in s, "match_rules block not found"
s = s.replace(old, new)
io.open(p, 'w', encoding='utf-8').write(s)
print("done")
