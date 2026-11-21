"""Golden fix + tint the carried missile with its vehicle's batch colour, the way Mine.draw tints a carried mine."""
p = "/app/core/src/com/agateau/pixelwheels/bonus/Missile.java"
s = open(p).read()
old = """        if (zLevel == ZLevel.FLYING_LOW) {
            // Draw the shadow at Z_FLYING so that the shadow is drawn *over* its vehicle
            drawShadow(batch);
            drawMissile(batch);
"""
new = """        if (zLevel == ZLevel.FLYING_LOW) {
            // Draw the shadow at Z_FLYING so that the shadow is drawn *over* its vehicle
            if (mStatus == Status.WAITING) {
                batch.setColor(mShooter.getVehicleRenderer().getBatchColor());
            }
            drawShadow(batch);
            drawMissile(batch);
            batch.setColor(Color.WHITE);
"""
assert s.count(old) == 1, "anchor not found"
open(p, "w").write(s.replace(old, new, 1))
print("ALT_TINT applied")
