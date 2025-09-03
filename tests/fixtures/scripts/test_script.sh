#!/bin/bash

# Test script for phazr integration tests

echo "Starting test script..."
echo "Arguments: $@"
echo "Environment: $ENVIRONMENT"
echo "Namespace: $NAMESPACE"

# Simulate some work
sleep 1

# Check for test conditions
if [ "$1" = "fail" ]; then
    echo "Script configured to fail" >&2
    exit 1
fi

if [ "$1" = "slow" ]; then
    echo "Running slow operation..."
    sleep 5
fi

echo "Test script completed successfully"
exit 0