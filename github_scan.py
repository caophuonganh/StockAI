# -*- coding: utf-8 -*-
import json
import backend

result = backend.scan_once()
print(json.dumps(result, ensure_ascii=False, indent=2))
