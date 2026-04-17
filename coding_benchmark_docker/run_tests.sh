#!/bin/bash
# Coding benchmark Docker entrypoint
# Builds the LLM-generated app, starts it, runs Playwright tests, outputs JSON results

set -o pipefail

RESULT_FILE="/screenshots/results.json"
mkdir -p /screenshots

# Helper: output result and exit
output_result() {
  echo "$1" > "$RESULT_FILE"
  echo "$1"
  exit 0
}

cd /app

# ============================================================
# Phase 1: npm install
# ============================================================
echo "=== Phase 1: npm install ===" >&2
if [ ! -f package.json ]; then
  output_result '{"build_success": false, "server_starts": false, "error": "No package.json found"}'
fi

timeout 120 npm install --legacy-peer-deps 2>&1 >&2
if [ $? -ne 0 ]; then
  output_result '{"build_success": false, "server_starts": false, "error": "npm install failed"}'
fi

# ============================================================
# Phase 2: Build (if build script exists)
# ============================================================
echo "=== Phase 2: Build ===" >&2
if grep -q '"build"' package.json 2>/dev/null; then
  timeout 120 npm run build 2>&1 >&2
  # Build failure is not fatal - some setups use dev server
fi

echo '{"build_success": true}' >&2

# ============================================================
# Phase 3: Start servers
# ============================================================
echo "=== Phase 3: Start servers ===" >&2
if [ -f start.sh ]; then
  chmod +x start.sh
  bash start.sh &
elif grep -q '"start"' package.json 2>/dev/null; then
  npm start &
elif grep -q '"dev"' package.json 2>/dev/null; then
  npm run dev &
else
  # Try to start server.js or index.js directly
  if [ -f server.js ]; then
    node server.js &
  elif [ -f backend/server.js ]; then
    node backend/server.js &
  elif [ -f src/server.js ]; then
    node src/server.js &
  fi
  # Also try starting frontend
  if [ -d client ] || [ -d frontend ]; then
    cd client 2>/dev/null || cd frontend 2>/dev/null
    npm install --legacy-peer-deps 2>&1 >&2
    npm start &
    cd /app
  fi
fi

# ============================================================
# Phase 4: Wait for servers
# ============================================================
echo "=== Phase 4: Waiting for servers ===" >&2
FRONTEND_READY=false
BACKEND_READY=false

for i in $(seq 1 45); do
  if ! $FRONTEND_READY; then
    curl -s http://localhost:3000 > /dev/null 2>&1 && FRONTEND_READY=true
  fi
  if ! $BACKEND_READY; then
    curl -s http://localhost:3001 > /dev/null 2>&1 && BACKEND_READY=true
    # Some apps serve everything on 3000
    curl -s http://localhost:3000/api/users > /dev/null 2>&1 && BACKEND_READY=true
  fi
  if $FRONTEND_READY; then
    break
  fi
  sleep 1
done

if ! $FRONTEND_READY; then
  output_result '{"build_success": true, "server_starts": false, "error": "Frontend server did not start on port 3000 within 45s"}'
fi

echo "Frontend ready: $FRONTEND_READY, Backend ready: $BACKEND_READY" >&2

# ============================================================
# Phase 5: Run Playwright tests
# ============================================================
echo "=== Phase 5: Running Playwright tests ===" >&2
cd /test
npx playwright test --config=tests/playwright.config.ts 2>&1 >&2 || true

# ============================================================
# Phase 6: Collect results
# ============================================================
echo "=== Phase 6: Collecting results ===" >&2

# Read individual test results
LOGIN_RESULT=$(cat /screenshots/test_login.json 2>/dev/null || echo '{"passed": false}')
FRIENDS_RESULT=$(cat /screenshots/test_friends.json 2>/dev/null || echo '{"passed": false}')
MSG_RESULT=$(cat /screenshots/test_messaging.json 2>/dev/null || echo '{"passed": false}')
REALTIME_RESULT=$(cat /screenshots/test_realtime.json 2>/dev/null || echo '{"passed": false}')

# Check screenshots exist
HAS_LOGIN_SS=$([ -f /screenshots/login.png ] && echo true || echo false)
HAS_FRIENDS_SS=$([ -f /screenshots/friends.png ] && echo true || echo false)
HAS_DM_SS=$([ -f /screenshots/dm.png ] && echo true || echo false)
HAS_CHAT_SS=$([ -f /screenshots/chat.png ] && echo true || echo false)

cat > "$RESULT_FILE" << ENDJSON
{
  "build_success": true,
  "server_starts": true,
  "test_login": $LOGIN_RESULT,
  "test_friends": $FRIENDS_RESULT,
  "test_messaging": $MSG_RESULT,
  "test_realtime": $REALTIME_RESULT,
  "screenshots": {
    "login": $HAS_LOGIN_SS,
    "friends": $HAS_FRIENDS_SS,
    "dm": $HAS_DM_SS,
    "chat": $HAS_CHAT_SS
  }
}
ENDJSON

cat "$RESULT_FILE"
