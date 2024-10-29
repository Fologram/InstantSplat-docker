Start script (vast):
```
echo "Compiling curope for spann3r"
cd /workspace/InstantSplat/spann3r/croco/models/curope
conda run -n spann3r python setup.py build_ext --inplace

echo "Configuring 2DGS"
conda env update -n surfel_splatting --file /workspace/InstantSplat/2d-gaussian-splatting/environment.yml

echo "Starting cloudflare tunnel"
cloudflared tunnel --no-autoupdate --url http://localhost:5000 > /tmp/cloudflared.log 2>&1 &
echo "Cloudflared started with PID $!" >> /tmp/startup.log
mkdir -p /tmp

# Wait for the URL to appear in the log file
while ! grep -q "+--*+" /tmp/cloudflared.log; do
  sleep 1
done

# Extract and display the URL - modified to handle the specific log format
TUNNEL_URL=$(grep -A 2 "+--*+" /tmp/cloudflared.log | grep "https://" | sed -E 's/.*https:\/\/([^[:space:]]*).*/\1/')
echo "======== CLOUDFLARED TUNNEL URL ========"
echo "https://$TUNNEL_URL"
echo "========================================"

echo "Starting server..."
cd /workspace/InstantSplat
pixi run python server.py --listen 0.0.0.0 --port 5000 > /tmp/server.log 2>&1 &
```
