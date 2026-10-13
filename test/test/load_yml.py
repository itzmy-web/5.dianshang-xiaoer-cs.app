# itzmy/test/yaml/load_yml.py

import yaml

with open("test.yml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

print(data)