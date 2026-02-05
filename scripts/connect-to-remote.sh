#!/bin/bash
# scripts/connect-to-remote.sh
# Establishes an SSH tunnel to the remote Typesense server on nathan-server.

REMOTE_HOST="nathan-server"
REMOTE_PORT="8108"
LOCAL_PORT="8108"

echo "Checking for existing process on port $LOCAL_PORT..."
PID=$(lsof -t -i:$LOCAL_PORT)
if [ -n "$PID" ]; then
    echo "Port $LOCAL_PORT is already in use by PID $PID."
    echo "This might be a local Typesense instance or an existing tunnel."
    read -p "Do you want to kill it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kill $PID
        echo "Killed process $PID."
        sleep 1
    else
        echo "Aborting. Please free port $LOCAL_PORT."
        exit 1
    fi
fi

echo "Starting SSH tunnel to $REMOTE_HOST..."
# -N: Do not execute a remote command.
# -L: Specifies that the given port on the local (client) host is to be forwarded to the given host and port on the remote side.
# -f: Requests ssh to go to background just before command execution.
ssh -f -N -L $LOCAL_PORT:localhost:$REMOTE_PORT $REMOTE_HOST

if [ $? -eq 0 ]; then
    echo "✓ SSH Tunnel established."
    echo "  Local: localhost:$LOCAL_PORT -> Remote: $REMOTE_HOST:$REMOTE_PORT"
    echo "  You can close the tunnel by finding the ssh process: 'ps aux | grep ssh' and killing it."
else
    echo "✗ Failed to establish SSH tunnel."
    exit 1
fi
