#!/bin/bash
set -e

echo "=== Testing Sandbox Isolation ==="

# Give services time to start
sleep 2

echo ""
echo "[1] Testing external egress BLOCKED..."
if docker exec agent-tester curl -s --max-time 5 8.8.8.8 > /dev/null 2>&1; then
  echo "FAIL: Agent can reach external internet (8.8.8.8)!"
  exit 1
else
  echo "PASS: External egress blocked (8.8.8.8 unreachable)"
fi

echo ""
echo "[2] Testing external DNS BLOCKED..."
if docker exec agent-tester curl -s --max-time 5 https://google.com > /dev/null 2>&1; then
  echo "FAIL: Agent can reach external HTTPS!"
  exit 1
else
  echo "PASS: External DNS/HTTPS blocked"
fi

echo ""
echo "[3] Testing Hub is reachable from agent..."
if docker exec agent-tester curl -s --max-time 5 http://hub:8080/ping | grep -q '"status"'; then
  echo "PASS: Hub reachable at http://hub:8080/ping"
else
  echo "FAIL: Cannot reach Hub from agent container"
  exit 1
fi

echo ""
echo "[4] Testing agent-to-agent messaging via Hub..."
# Register two agents and send a message between them
docker exec agent-tester python -c "
import requests, json
r = requests.post('http://hub:8080/agents/register', json={'name': 'agent-tester', 'agent_type': 'test'})
print('Registered agent-tester:', r.status_code)
r = requests.post('http://hub:8080/messages/send', json={
    'from_agent': 'agent-tester',
    'to_agent': 'agent-tester-2',
    'content': 'Hello from test!',
    'message_type': 'text'
})
print('Sent message:', r.status_code, r.json().get('id', 'no id'))
"
if [ $? -eq 0 ]; then
  echo "PASS: Agent can send messages via Hub"
else
  echo "FAIL: Agent messaging failed"
  exit 1
fi

echo ""
echo "=== ALL ISOLATION TESTS PASSED ==="
