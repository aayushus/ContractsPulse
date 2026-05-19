#!/bin/bash

echo "🔄 Gracefully shutting down ContractsPulse..."
docker-compose down

echo "🧹 Cleaning up orphaned containers (if any)..."
docker-compose rm -f

echo "🚀 Rebuilding and starting services..."
docker-compose up -d --build

echo "✅ Restart complete! The app is running in the background."
echo "👉 Frontend: http://localhost:5173"
echo "👉 Backend API: http://localhost:9432"
echo "💡 To view logs, run: docker-compose logs -f"
