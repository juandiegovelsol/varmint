-- tree trunk at TX,TZ; terrace level G (ground node level)
local TX, TZ, G = 61, -3, 8
local fill = {}
-- terrace: grass top at G, dirt below, air above (carved into the hill)
for dx = -9, 5 do for dz = -5, 9 do
	local r = math.max(math.abs(dx + 2) / 7.5, math.abs(dz - 2) / 7.5)
	if r <= 1 then
		for y = -3, -1 do fill[#fill+1] = {dx, y, dz, "default:dirt"} end
		fill[#fill+1] = {dx, 0, dz, "default:dirt_with_grass"}
		for y = 1, 12 do fill[#fill+1] = {dx, y, dz, "air"} end
	end
end end
-- L-shaped fence: X leg from the trunk going west, Z leg going north with a gate
for x = -5, -1 do
	if x == -3 then fill[#fill+1] = {x, 1, 0, "doors:gate_wood_closed", 2}
	else fill[#fill+1] = {x, 1, 0, "default:fence_wood"} end
end
for z = 1, 6 do fill[#fill+1] = {-5, 1, z, "default:fence_wood"} end
-- grass tufts on the terrace
for _, g in ipairs({{-3,2},{-2,4},{0,3},{1,5},{-4,-2},{2,-2},{-1,7},{3,1},{-7,4},{-6,7},{2,7},{-3,-4},{-8,1}}) do
	fill[#fill+1] = {g[1], 1, g[2], "default:grass_" .. (3 + (g[1] + g[2]) % 3)}
end
-- canopy (relative to ground level G)
local leaves = {}
local function L(dx, y, dz, n) leaves[#leaves+1] = {dx, y, dz, n} end
for y = 3, 6 do
	local r = (y == 3 or y == 6) and 1 or 2
	for dx = -r, r do for dz = -r, r do
		if not (r == 2 and math.abs(dx) == 2 and math.abs(dz) == 2) then
			L(dx, y, dz)
		end
	end end
end
-- apples hang on the outside of the canopy (replace a few leaves first)
local apples = {{2, 4, 0}, {-2, 4, 1}, {0, 4, 2}, {1, 3, -1}, {-1, 5, -2}, {2, 5, -1}}
for _, a in ipairs(apples) do table.insert(leaves, 1, {a[1], a[2], a[3], "default:apple"}) end

return {
	leaves_scale = 1.1,
	clear = 9,
	area = {{x = 30, y = -10, z = -40}, {x = 100, y = 60, z = 30}},
	trees = {{x = TX, z = TZ, ground = G, trunk = 5, fill = fill, leaves = leaves}},
	settle = 8,
	path = {
		{t = 0,  pos = {x = 70, y = 13.5, z = -15},   target = {x = 58.5, y = 10.5, z = -0.5}},
		{t = 5,  pos = {x = 66, y = 11.5, z = -12},   target = {x = 59, y = 11, z = -1}},
		{t = 9,  pos = {x = 61.5, y = 9.2, z = -10.5}, target = {x = 61, y = 12, z = -2}},
		{t = 12, pos = {x = 60, y = 9.2, z = -9.5},   target = {x = 58, y = 10, z = -3}},
		{t = 15, pos = {x = 57.5, y = 12.5, z = -8}, target = {x = 58, y = 9, z = -3}},
		{t = 19, pos = {x = 50, y = 10.5, z = -6},   target = {x = 56, y = 9.5, z = 0.5}},
		{t = 22, pos = {x = 52, y = 11, z = 6.5},    target = {x = 56, y = 9.5, z = 1.5}},
		{t = 25, pos = {x = 56, y = 21, z = -9},     target = {x = 61, y = 12, z = -2}},
		{t = 28, pos = {x = 63, y = 22, z = -7},     target = {x = 61, y = 12, z = -2}},
	},
}
