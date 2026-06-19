#!/usr/bin/env python3
import json, requests, time, sys
from pathlib import Path

print(f"[{time.strftime('%H:%M:%S')}] 开始测试 Kimi Claw 后台调用", flush=True)

with open(Path.home() / '.kimi/kimi-claw/openclaw.json') as f:
    config = json.load(f)

provider = config['models']['providers']['kimi-coding']
url = f"{provider['baseUrl']}/v1/messages"
headers = {
    "Authorization": f"Bearer {provider['apiKey']}",
    "Content-Type": "application/json",
    **provider.get('headers', {})
}
payload = {
    "model": provider['models'][0]['id'],
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "请为'清代花卉刺绣'写一段30字的艺术评鉴。"}]
}

start = time.time()
try:
    r = requests.post(url, headers=headers, json=payload, timeout=(10, 60))
    elapsed = time.time() - start
    print(f"[{time.strftime('%H:%M:%S')}] 请求返回，耗时 {elapsed:.1f}s, status={r.status_code}", flush=True)
    if r.status_code == 200:
        data = r.json()
        texts = [item.get('text', '') for item in data.get('content', []) if item.get('type') == 'text']
        print(f"[{time.strftime('%H:%M:%S')}] 结果: {texts[0][:100] if texts else 'empty'}", flush=True)
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 错误: {r.text[:200]}", flush=True)
except Exception as e:
    elapsed = time.time() - start
    print(f"[{time.strftime('%H:%M:%S')}] 异常，耗时 {elapsed:.1f}s: {e}", flush=True)

print(f"[{time.strftime('%H:%M:%S')}] 测试结束", flush=True)
