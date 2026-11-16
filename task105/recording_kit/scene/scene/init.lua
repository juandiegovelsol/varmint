-- Scripted recording scene: fixed tree, fixed camera path, no manual input.
minetest.send_join_message = function() end
minetest.send_leave_message = function() end
minetest.get_server_status = function() return "" end
local P = dofile(minetest.get_modpath("scene") .. "/params.lua")

if P.leaves_scale then
	minetest.override_item("default:leaves", {visual_scale = P.leaves_scale})
end
for name, def in pairs(P.overrides or {}) do
	minetest.override_item(name, def)
end

local ground = {}
local function find_ground(x, z)
	for y = 80, -20, -1 do
		local n = minetest.get_node({x = x, y = y, z = z}).name
		local d = minetest.registered_nodes[n]
		if n ~= "air" and n ~= "ignore" and d and d.walkable and
				minetest.get_item_group(n, "tree") == 0 and
				minetest.get_item_group(n, "leaves") == 0 then
			return y
		end
	end
	return 0
end

local function build(tree)
	local x, z = tree.x, tree.z
	local g = tree.ground or find_ground(x, z)
	tree.g = g
	-- clear natural vegetation around the spot
	for dx = -P.clear, P.clear do for dz = -P.clear, P.clear do for y = g - 3, g + 14 do
		local pos = {x = x + dx, y = y, z = z + dz}
		local n = minetest.get_node(pos).name
		if minetest.get_item_group(n, "tree") > 0 or minetest.get_item_group(n, "leaves") > 0
				or n == "default:apple" then
			minetest.set_node(pos, {name = "air"})
		end
	end end end
	for _, f in ipairs(tree.fill or {}) do
		minetest.set_node({x = x + f[1], y = g + f[2], z = z + f[3]}, {name = f[4], param2 = f[5] or 0})
	end
	local h = tree.trunk or 5
	for y = 1, h do
		minetest.set_node({x = x, y = g + y, z = z}, {name = tree.trunk_node or "default:tree"})
	end
	for _, l in ipairs(tree.leaves) do
		local pos = {x = x + l[1], y = g + l[2], z = z + l[3]}
		if minetest.get_node(pos).name == "air" then
			minetest.set_node(pos, {name = l[4] or "default:leaves", param2 = l[5] or 0})
		end
	end
	minetest.log("action", ("[scene] tree at %d,%d,%d ground %d"):format(x, g + 1, z, g))
end

local ready = false
local t0
local function lerp(a, b, s) return a + (b - a) * s end

minetest.register_on_joinplayer(function(player)
	local name = player:get_player_name()
	minetest.set_player_privs(name, {fly = true, noclip = true, fast = true, interact = true})
	player:hud_set_flags({hotbar = false, healthbar = false, crosshair = false,
		wielditem = false, breathbar = false, minimap = false, minimap_radar = false})
	player:set_physics_override({gravity = 0, speed = 0, jump = 0})
	player:set_properties({visual_size = {x = 0, y = 0}, makes_footstep_sound = false})
	minetest.set_timeofday(P.time or 0.5)
	local k = P.path[1]
	player:set_pos(k.pos)
	local minp = vector.new(P.area[1]); local maxp = vector.new(P.area[2])
	minetest.emerge_area(minp, maxp, function(_, _, remaining)
		if remaining == 0 then
			minetest.after(1.0, function()
				for _, tree in ipairs(P.trees) do build(tree) end
				for _, tree in ipairs(P.trees) do
					minetest.log("action", ("[scene] ground_of %d,%d = %d"):format(tree.x, tree.z, tree.g))
				end
				if P.survey then
					for _, s in ipairs(P.survey) do
						minetest.log("action", ("[scene] survey %d,%d = %d"):format(s[1], s[2], find_ground(s[1], s[2])))
					end
				end
				local fl = io.open(minetest.get_worldpath() .. "/scene_loaded", "w"); if fl then fl:write("1"); fl:close() end
				minetest.after(P.settle or 6, function() ready = true; t0 = minetest.get_us_time() end)
			end)
		end
	end)
end)

local function key_at(t)
	local path = P.path
	local function look(pos, tg)
		local dx, dy, dz = tg.x - pos.x, tg.y - (pos.y + 1.625), tg.z - pos.z
		local yaw = math.deg(math.atan2(-dx, dz))
		local pitch = math.deg(math.atan2(-dy, math.sqrt(dx * dx + dz * dz)))
		return {pos = pos, yaw = yaw, pitch = pitch}
	end
	if t <= path[1].t then return look(path[1].pos, path[1].target) end
	for i = 1, #path - 1 do
		local a, b = path[i], path[i + 1]
		if t <= b.t then
			local s = (t - a.t) / (b.t - a.t)
			s = s * s * (3 - 2 * s)
			local function lv(u, v) return {x = lerp(u.x, v.x, s), y = lerp(u.y, v.y, s), z = lerp(u.z, v.z, s)} end
			return look(lv(a.pos, b.pos), lv(a.target, b.target))
		end
	end
	local e = path[#path]
	return look(e.pos, e.target)
end

local done = false
minetest.register_globalstep(function()
	local player = minetest.get_player_by_name("rec")
	if not player then return end
	if not ready then
		local k = key_at(0)
		player:set_pos(k.pos); player:set_look_horizontal(math.rad(k.yaw)); player:set_look_vertical(math.rad(k.pitch))
		return
	end
	local t = (minetest.get_us_time() - t0) / 1e6
	if t == 0 then return end
	if not done then
		local f = io.open(minetest.get_worldpath() .. "/scene_started", "w")
		if f then f:write("1"); f:close() end
		done = true
	end
	local k = key_at(t)
	player:set_pos(k.pos)
	player:set_look_horizontal(math.rad(k.yaw))
	player:set_look_vertical(math.rad(k.pitch))
	if t > P.path[#P.path].t + 0.5 then
		local f = io.open(minetest.get_worldpath() .. "/scene_done", "w")
		if f then f:write("1"); f:close() end
	end
end)
