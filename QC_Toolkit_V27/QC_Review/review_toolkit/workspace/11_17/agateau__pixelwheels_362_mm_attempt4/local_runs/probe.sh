#!/bin/bash
cd /app/core/src/com/agateau/pixelwheels
sed -n 20,57p racer/VehicleRenderer.java
echo ----
grep -n "^public\|^final\|class Racer" racer/Racer.java | head -5
