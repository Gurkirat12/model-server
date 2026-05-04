#!/usr/bin/env bash
set -euo pipefail

IMAGE="model-server:latest"
PORT=8000
CONTAINER=""

PASS=0
FAIL=0

pass() { echo "  ✅ PASS: $1"; ((PASS++)); }
fail() { echo "  ❌ FAIL: $1"; ((FAIL++)); }

wait_ready() {
    local max=90
    local i=0
    echo "  ⏳ Waiting for /v1/health/ready (up to ${max}s)..."
    while [ $i -lt $max ]; do
        status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/v1/health/ready 2>/dev/null || echo "000")
        if [ "$status" = "200" ]; then
            echo "  ✅ Ready after ${i}s"
            return 0
        fi
        sleep 1
        ((i++))
    done
    echo "  ❌ Timed out waiting for ready"
    return 1
}

cleanup() {
    if [ -n "$CONTAINER" ]; then
        echo ""
        echo "Stopping container $CONTAINER..."
        docker stop "$CONTAINER" >/dev/null 2>&1 || true
        docker rm "$CONTAINER" >/dev/null 2>&1 || true
        CONTAINER=""
    fi
}

trap cleanup EXIT

test_profile() {
    local profile="$1"
    echo ""
    echo "============================================================"
    echo " Testing profile: $profile"
    echo "============================================================"

    CONTAINER=$(docker run -d \
        -e PROFILE="$profile" \
        -p ${PORT}:8000 \
        --name "model-server-test-${profile}" \
        "$IMAGE")

    echo "  Container: $CONTAINER"

    sleep 3
    live_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/v1/health/live 2>/dev/null || echo "000")
    if [ "$live_status" = "200" ]; then
        pass "/v1/health/live returns 200 immediately"
    else
        fail "/v1/health/live returned $live_status (expected 200)"
    fi

    if ! wait_ready; then
        fail "/v1/health/ready never returned 200"
        cleanup
        return
    fi
    pass "/v1/health/ready returns 200 after model load"

    profiles_resp=$(curl -s http://localhost:$PORT/v1/profiles)
    active=$(echo "$profiles_resp" | jq -r '.active_profile' 2>/dev/null || echo "")
    if [ "$active" = "$profile" ]; then
        pass "/v1/profiles reports active_profile='$profile'"
    else
        fail "/v1/profiles reported '$active' (expected '$profile')"
    fi

    models_resp=$(curl -s http://localhost:$PORT/v1/models)
    model_count=$(echo "$models_resp" | jq '.data | length' 2>/dev/null || echo "0")
    if [ "$model_count" -ge 1 ]; then
        model_name=$(echo "$models_resp" | jq -r '.data[0].id' 2>/dev/null || echo "?")
        pass "/v1/models returns model: $model_name"
    else
        fail "/v1/models returned no models"
    fi

    chat_resp=$(curl -s -X POST http://localhost:$PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{"messages": [{"role": "user", "content": "Reply with exactly one word: Hello"}], "max_tokens": 20}')
    content=$(echo "$chat_resp" | jq -r '.choices[0].message.content' 2>/dev/null || echo "")
    if [ -n "$content" ] && [ "$content" != "null" ]; then
        pass "/v1/chat/completions returned: \"$(echo "$content" | head -c 60)\""
    else
        fail "/v1/chat/completions failed — response: $chat_resp"
    fi

    cli_out=$(docker exec "model-server-test-${profile}" list-profiles 2>/dev/null || echo "")
    if echo "$cli_out" | grep -q "$profile"; then
        pass "list-profiles CLI shows active profile '$profile'"
    else
        fail "list-profiles CLI did not show '$profile'"
    fi

    cleanup
}

test_invalid_profile() {
    echo ""
    echo "============================================================"
    echo " Testing invalid profile rejection"
    echo "============================================================"

    exit_code=0
    docker run --rm -e PROFILE=invalid "$IMAGE" 2>/dev/null || exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        pass "Container exits non-zero on PROFILE=invalid"
    else
        fail "Container should fail fast on invalid PROFILE"
    fi
}

print_summary() {
    echo ""
    echo "============================================================"
    echo " Test Summary"
    echo "============================================================"
    echo "  Passed: $PASS"
    echo "  Failed: $FAIL"
    echo ""
    if [ "$FAIL" -eq 0 ]; then
        echo "  🎉 All tests passed!"
        exit 0
    else
        echo "  ⚠️  Some tests failed."
        exit 1
    fi
}

echo "============================================================"
echo " Building image: $IMAGE"
echo "============================================================"
docker build -t "$IMAGE" .

for profile in balanced throughput latency; do
    test_profile "$profile"
done

test_invalid_profile
print_summary
