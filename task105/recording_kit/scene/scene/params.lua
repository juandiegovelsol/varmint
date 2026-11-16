-- tree trunk at TX,TZ; terrace level G (ground node level)
local TX, TZ, G = 61, -3, 8
local fill = {}
local function put(dx, y, dz, name, param2) fill[#fill+1] = {dx, y, dz, name, param2} end
-- terrace: grass top at G, dirt below, air above (carved into the hill)
for dx = -9, 5 do for dz = -5, 9 do
	local r = math.max(math.abs(dx + 2) / 7.5, math.abs(dz - 2) / 7.5)
	if r <= 1 then
		for y = -3, -1 do put(dx, y, dz, "default:dirt") end
		put(dx, 0, dz, "default:dirt_with_grass")
		for y = 1, 12 do put(dx, y, dz, "air") end
	end
end end
-- L-shaped fence: X leg from the trunk going west, Z leg going north with a gate
for x = -5, -1 do
	if x == -3 then put(x, 1, 0, "doors:gate_wood_closed", 2)
	else put(x, 1, 0, "default:fence_wood") end
end
for z = 1, 6 do put(-5, 1, z, "default:fence_wood") end
-- grass tufts on the terrace
for _, g in ipairs({{-3,2},{-2,4},{0,3},{1,5},{-4,-2},{2,-2},{3,1},{-7,4},{-6,7},{2,7},{-8,1}}) do
	put(g[1], 1, g[2], "default:grass_" .. (3 + (g[1] + g[2]) % 3))
end
-- a stone channel along the south edge, fed by a water source at its west end
for dx = -9, -3 do
	put(dx, 1, -5, "default:stonebrick")
	put(dx, 1, -3, "default:stonebrick")
end
put(-9, 1, -4, "default:stonebrick")
put(-3, 1, -4, "default:stonebrick")
put(-8, 1, -4, "default:water_source")
-- a rail track: up a step at the west end, east, a curve north, and up a step
put(0, 1, -4, "default:cobble"); put(0, 2, -4, "carts:rail")
for dx = 1, 4 do put(dx, 1, -4, "carts:rail") end
for dz = -3, 0 do put(4, 1, dz, "carts:rail") end
put(4, 1, 1, "default:cobble"); put(4, 2, 1, "carts:rail")
put(5, 1, -2, "carts:rail") -- a short branch off the north-running leg
-- a stone post with a torch on each of its four sides
put(3, 1, 5, "default:stonebrick"); put(3, 2, 5, "default:stonebrick")
put(4, 2, 5, "default:torch_wall", 3)
put(2, 2, 5, "default:torch_wall", 2)
put(3, 2, 6, "default:torch_wall", 5)
put(3, 2, 4, "default:torch_wall", 4)
-- a 3 x 2 window of (connected) glass at the north side
for dx = -2, 0 do for y = 1, 2 do put(dx, y, 8, "default:glass") end end
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
	settle = 12,
	path = {
		-- the tree close up
		{t = 0,  pos = {x = 70, y = 13.5, z = -15},   target = {x = 58.5, y = 10.5, z = -0.5}},
		{t = 5,  pos = {x = 66, y = 11.5, z = -12},   target = {x = 59, y = 11, z = -1}},
		{t = 9,  pos = {x = 61.5, y = 9.2, z = -10.5}, target = {x = 61, y = 12, z = -2}},
		-- the fence up to the trunk
		{t = 12, pos = {x = 60, y = 9.2, z = -9.5},   target = {x = 58, y = 10, z = -3}},
		{t = 15, pos = {x = 57.5, y = 12.5, z = -8},  target = {x = 58, y = 9, z = -3}},
		-- the water channel
		{t = 18, pos = {x = 58.5, y = 12.5, z = -9.5}, target = {x = 54.5, y = 9, z = -7}},
		{t = 21, pos = {x = 55, y = 13, z = -3.5},    target = {x = 55, y = 9, z = -7}},
		-- the rail track
		{t = 24, pos = {x = 60.5, y = 12, z = -12},   target = {x = 63, y = 9, z = -6.5}},
		{t = 27, pos = {x = 69, y = 12, z = -9},      target = {x = 64.5, y = 9, z = -4.5}},
		-- the post with the torches, around it
		{t = 30, pos = {x = 67.5, y = 10.8, z = -0.5}, target = {x = 64, y = 10, z = 2}},
		{t = 33, pos = {x = 67, y = 10.8, z = 5.5},   target = {x = 64, y = 10, z = 2}},
		{t = 36, pos = {x = 60.5, y = 10.8, z = 0.5}, target = {x = 64, y = 10, z = 2}},
		-- the glass window
		{t = 39, pos = {x = 60, y = 9.4, z = 1.5},    target = {x = 60, y = 10, z = 5}},
		{t = 42, pos = {x = 62, y = 9.8, z = 2.2},    target = {x = 60, y = 10, z = 5}},
		-- everything from above (rising east of the tree, clear of its canopy)
		{t = 44.5, pos = {x = 63.5, y = 17.5, z = 4.5}, target = {x = 60, y = 10, z = 2}},
		{t = 49, pos = {x = 60, y = 24, z = -13},     target = {x = 59, y = 9, z = -1}},
	},
}
