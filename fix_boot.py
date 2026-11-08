import io
p = 'tests/test_routing_fixes.py'
s = io.open(p, encoding='utf-8').read()
old = '''        config.set_value("allowed_folders", json.dumps([str(ws)]))
        config.set_value("default_work_folder", str(ws))
        _STATE["ws"] = ws'''
new = '''        config.set_value("allowed_folders", json.dumps([str(ws)]))
        config.set_value("default_work_folder", str(ws))
        # Train a model so behaviour is deterministic regardless of any model
        # another test file may have registered globally.
        train.train_all(42, kinds=["m1_logreg"], write_report=False)
        _STATE["ws"] = ws'''
assert old in s, "boot block not found"
s = s.replace(old, new)
io.open(p, 'w', encoding='utf-8').write(s)
print("done")
